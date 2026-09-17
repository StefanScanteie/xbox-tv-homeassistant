"""Config flow for Xbox TV."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CLIENT_ID,
    CONF_LIVE_ID,
    CONF_TOKENS,
    DEFAULT_NAME,
    DOMAIN,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    is_valid_host,
    is_valid_live_id,
)
from .xbox_api import (
    build_authorize_url,
    exchange_code_for_tokens,
    extract_oauth_code,
)

_LOGGER = logging.getLogger(__name__)


class XboxTvConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Xbox TV."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._name: str = DEFAULT_NAME
        self._host: str = ""
        self._live_id: str = ""
        self._reconfigure_entry: Any = None
        self._reconfigure: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not is_valid_host(user_input["host"]):
                errors["base"] = "invalid_host"
            elif not is_valid_live_id(user_input[CONF_LIVE_ID]):
                errors["base"] = "invalid_live_id"
            else:
                live_id = user_input[CONF_LIVE_ID].strip().upper()
                await self.async_set_unique_id(live_id)
                self._abort_if_unique_id_configured()
                self._name = user_input["name"]
                self._host = user_input["host"]
                self._live_id = live_id
                return await self.async_step_auth_choice()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=DEFAULT_NAME): str,
                    vol.Required("host"): str,
                    vol.Required(CONF_LIVE_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_auth_choice(
        self, user_input: str | None = None
    ) -> ConfigFlowResult:
        """Choose Microsoft sign-in or skip."""
        if user_input is not None:
            if user_input == "sign_in":
                return await self.async_step_oauth()
            return self._async_create_or_update_entry()

        return self.async_show_menu(
            step_id="auth_choice",
            menu_options=["sign_in", "skip"],
        )

    async def async_step_oauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle OAuth redirect URL."""
        client_id = OAUTH_CLIENT_ID
        authorize_url = build_authorize_url(client_id, OAUTH_REDIRECT_URI)
        errors: dict[str, str] = {}

        if user_input is not None:
            code = extract_oauth_code(user_input["redirect_url"])
            if code is None:
                errors["base"] = "invalid_code"
            else:
                session = async_get_clientsession(self.hass)
                try:
                    tokens = await exchange_code_for_tokens(session, code, client_id)
                except Exception:
                    _LOGGER.debug("OAuth token exchange failed", exc_info=True)
                    errors["base"] = "invalid_code"
                else:
                    return self._async_create_or_update_entry(tokens)

        return self.async_show_form(
            step_id="oauth",
            description_placeholders={"authorize_url": authorize_url},
            data_schema=vol.Schema({vol.Required("redirect_url"): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=vol.Schema(
                    {
                        vol.Required("name", default=reconfigure_entry.title): str,
                        vol.Required("host", default=reconfigure_entry.data["host"]): str,
                        vol.Required(
                            CONF_LIVE_ID,
                            default=reconfigure_entry.data[CONF_LIVE_ID],
                        ): str,
                    }
                ),
            )

        if not is_valid_host(user_input["host"]):
            errors["base"] = "invalid_host"
        elif not is_valid_live_id(user_input[CONF_LIVE_ID]):
            errors["base"] = "invalid_live_id"
        else:
            live_id = user_input[CONF_LIVE_ID].strip().upper()
            if live_id != reconfigure_entry.unique_id:
                await self.async_set_unique_id(live_id)
                self._abort_if_unique_id_configured()
            self._reconfigure_entry = reconfigure_entry
            self._reconfigure = True
            self._name = user_input["name"]
            self._host = user_input["host"]
            self._live_id = live_id
            return await self.async_step_reconfigure_auth()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=reconfigure_entry.title): str,
                    vol.Required("host", default=reconfigure_entry.data["host"]): str,
                    vol.Required(
                        CONF_LIVE_ID,
                        default=reconfigure_entry.data[CONF_LIVE_ID],
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_auth(
        self, user_input: str | None = None
    ) -> ConfigFlowResult:
        """Optionally refresh Microsoft tokens during reconfigure."""
        if user_input is not None:
            if user_input == "sign_in":
                return await self.async_step_oauth()
            return self._async_create_or_update_entry()

        return self.async_show_menu(
            step_id="reconfigure_auth",
            menu_options=["sign_in", "skip"],
        )

    def _async_create_or_update_entry(
        self, tokens: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create or update the config entry."""
        data: dict[str, Any] = {
            "name": self._name,
            "host": self._host,
            CONF_LIVE_ID: self._live_id,
            CONF_CLIENT_ID: OAUTH_CLIENT_ID,
        }
        if tokens is not None:
            data[CONF_TOKENS] = tokens
        elif self._reconfigure_entry is not None and CONF_TOKENS in self._reconfigure_entry.data:
            data[CONF_TOKENS] = self._reconfigure_entry.data[CONF_TOKENS]

        if self._reconfigure:
            assert self._reconfigure_entry is not None
            entry = self._reconfigure_entry
            if self.unique_id is not None and self.unique_id != entry.unique_id:
                self.hass.config_entries.async_update_entry(
                    entry, unique_id=self.unique_id
                )
            return self.async_update_reload_and_abort(
                entry,
                title=self._name,
                data=data,
            )

        return self.async_create_entry(title=self._name, data=data)
