# Navimow openHAB Bridge

Python bridge that polls the Navimow cloud and writes mower status to openHAB's REST API. It runs locally and requires an internet connection to the Navimow cloud.

**Experimental — community testing welcome.** This version was prepared from an existing installation using `navimow-sdk` 0.1.2, but the revised code has not been tested against a live mower or openHAB installation. Nine offline regression tests have passed. The supplied service and item definitions are new examples.

Please report results through GitHub Issues, including your mower model, Python and openHAB versions, the steps you followed, and relevant logs with tokens, credentials and personal identifiers removed. Reports on login, automatic token refresh, status updates and the example page are especially useful.

## How status reaches openHAB

```text
Navimow cloud --HTTPS API--> Python poller --HTTP(S) REST API--> openHAB items
```

Every polling cycle (five minutes by default), `navimow_to_openhab.py` calls the SDK's `async_get_device_status()` to fetch the mower's status from the Navimow cloud over HTTPS.

The poller's `oh_put_state()` function then writes each relevant value directly to openHAB with an HTTP `PUT` to `/rest/items/<item-name>/state`. For example, it sends `DOCKED` to `/rest/items/Navimow_Status/state` and `85` to `/rest/items/Navimow_Battery/state`. The server address comes from `openhab_base_url` in `config.json`.

## Features

- Status, battery, vehicle state and error reporting every five minutes by default.
- Token refresh with validation and atomic token-file replacement.
- One refresh attempt after an API authentication error; polling retries on the next interval.
- Successful-transfer heartbeat on every poll, even when status is unchanged.
- CLI commands for device discovery, status, start, pause, resume and dock.

## Requirements

- Python 3.11 or later; Linux with systemd for the service example.
- A Navimow account and mower supported by SDK 0.1.2.
- Working OAuth client credentials and a permitted redirect URI. Credentials are not shipped.
- openHAB with the items in `examples/navimow.items` and REST access.

The example OAuth endpoints and `homeassistant` client ID come from the supplied installation's European configuration. They are not a guarantee that this client registration permits arbitrary users or redirects. Use credentials and endpoints appropriate to your setup. The original `CLIENT_SECRET` setting must be transferred privately into `config.json` or `NAVIMOW_CLIENT_SECRET`.

## Install and configure

Place the project at `/opt/navimow-openhab-bridge` on the intended Linux host, then:

```bash
cd /opt/navimow-openhab-bridge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp config.example.json config.json
chmod 600 config.json
```

Edit `config.json`:

- Set `oauth.client_secret` privately, or supply the environment variable `NAVIMOW_CLIENT_SECRET`.
- Set `openhab_base_url` to the openHAB server base URL, without `/rest/items`.
- Set `openhab_api_token` if authentication is required. The bridge uses the token as the HTTP Basic username with an empty password.
- After discovery, set `device_id` to your mower ID.
- Adjust `poll_seconds` if needed; values below 30 seconds are rejected.

Paths in `tokens_file` are resolved relative to the configuration file. `NAVIMOW_CONFIG` can select a different configuration path. Protect any custom configuration and token paths yourself: `.gitignore` covers the default filenames only.

## Login

Stop any bridge process before logging in or manually refreshing tokens. Only one process should write the shared token file at a time.

```bash
.venv/bin/python navimow_login.py
.venv/bin/python navimowctl.py devices
```

The login opens a browser, validates the callback state, exchanges the authorization code and saves tokens without printing them. It waits up to five minutes. A rejected or incomplete token response leaves existing tokens untouched.

For a headless server, open an SSH connection from your browser computer with local forwarding:

```bash
ssh -L 8765:127.0.0.1:8765 USER@SERVER
```

Run the login script on the server in that connection and open its printed URL in the local browser. The example callback is `http://127.0.0.1:8765/callback`.

You may instead privately migrate the existing `navimow_tokens.json` while the old service is stopped. The account credentials and endpoints must match. Do not operate the old and new service simultaneously against the same refresh-token chain.

## openHAB

Add the item definitions from `examples/navimow.items` to your openHAB configuration, avoiding duplicate item names. Start in the foreground:

```bash
.venv/bin/python navimow_to_openhab.py
```

`Navimow_Online` indicates whether the last bridge cycle succeeded, not the mower's own online flag. It does not automatically turn off if the bridge process or host stops. Monitor the age of `Navimow_LastUpdate` for that case.

`Navimow_LastUpdate` records the last successful transfer to openHAB. It is written after status values and `Online`, and changes every successful poll. On failure, the bridge attempts to set `Online` to `OFF` and preserves the last successful timestamp. This differs from the supplied script, which also updated the timestamp after failures.

Status fields are written only when the status payload changes. `Navimow_LastUpdate` and `Navimow_Online` are updated on every successful poll.

### Example status page

[`examples/navimow-page.yaml`](examples/navimow-page.yaml) provides a Main UI layout page based on the supplied installation's page. It uses standard openHAB components to show status, battery level, vehicle state, errors and the last successful update. Labels are in English. All seven referenced items are defined in [`examples/navimow.items`](examples/navimow.items); create these items before using the page.

The file follows openHAB's documented `version: 1` / `pages:` format, with the page UID `navimow`. On versions supporting file-based YAML pages, copy it into `$OPENHAB_CONF/yaml/` (usually `/etc/openhab/yaml/`). File-defined pages are read-only in Main UI; edit the YAML file to change them. Choose a different UID if `navimow` is already in use. See [YAML Pages](https://www.openhab.org/docs/configuration/yaml/pages.html) and [YAML Configuration](https://www.openhab.org/docs/configuration/yaml/).

Alternatively, create a Layout Page under **Settings → Pages** and open its **Code** tab. If the editor uses a `version:` / `pages:` wrapper, copy the definition into that structure, keeping the UID of the page you created. Older editors expose only the page body: copy the contents underneath `pages: → navimow:`, starting with `tags:`, and remove the four leading spaces from each line. Omit the `version:`, `pages:` and `navimow:` wrapper lines in that case. Save the page. Use either the file-based approach or the editor approach for a given page UID.

The page appears in the sidebar as **Navimow**. Its status card is green when `Navimow_Online` is `ON` and red otherwise. This reflects the last bridge cycle; check **Last Successful Update** for freshness if the bridge has stopped. The YAML structure and item references have been checked locally; the page still needs a visual check in your openHAB installation.

## Optional systemd service

The service example uses a dedicated `navimow` account and the new installation path. Adapt these if needed. On a new installation:

```bash
sudo useradd --system --home-dir /opt/navimow-openhab-bridge --shell /usr/sbin/nologin navimow
sudo chown -R navimow:navimow /opt/navimow-openhab-bridge
sudo chmod 600 /opt/navimow-openhab-bridge/config.json
sudo chmod 600 /opt/navimow-openhab-bridge/navimow_tokens.json
sudo cp examples/navimow-openhab.service /etc/systemd/system/navimow-openhab.service
sudo systemctl daemon-reload
sudo systemctl enable --now navimow-openhab.service
journalctl -u navimow-openhab.service -n 50 --no-pager
```

Run `useradd` only if the account does not already exist. If replacing an existing service, save its unit file and stop it before installing this example. Keep a private backup of the old installation for rollback. The service account needs write access to the token directory for atomic replacement.

## CLI

```bash
.venv/bin/python navimowctl.py devices
.venv/bin/python navimowctl.py status DEVICE_ID
.venv/bin/python navimowctl.py refresh
```

The commands `start`, `pause`, `resume` and `dock` also take `DEVICE_ID` and send real commands to the mower. Device discovery and status output can contain personal device identifiers; do not publish these outputs unredacted.

## Troubleshooting

- Missing config: create `config.json` from the example or set `NAVIMOW_CONFIG`.
- Missing or rejected refresh token: stop the service, run login, then restart it.
- HTTP errors from openHAB: check its address, API token and exact item names.
- `Poll OK, no status change`: polling succeeded; the heartbeat still updates.

No automatic password login is implemented. An invalid refresh token requires an interactive login. Token writers are not protected by an interprocess lock; stop the service before using manual login or refresh.

## Development and publication

```bash
python -m unittest discover -s tests -v
```

Tests use mocked cloud and openHAB responses and never command a mower. See [PREPARATION.md](PREPARATION.md) for validation coverage and areas needing community testing. The dependency is pinned to the version found in the copy; no claim is made that it is the latest release.

Upstream SDK: https://github.com/segwaynavimow/navimow-sdk

## License

This project is licensed under GNU GPL version 3 only (`GPL-3.0-only`); see [LICENSE](LICENSE). The copied SDK 0.1.2 package metadata declares MIT. The SDK itself and its virtual environment are not redistributed in this project.
