# Experimental release status

This version is intended for publication as an experimental community-testing release without prior live validation. The checks below describe what has been verified and what remains to be tested; live testing is not a prerequisite for this initial publication.

The partial source copy contains the essential project files. The openHAB poller and CLI were retained; shared configuration, token handling and login were revised for publication.

## Excluded from the project

- Existing tokens, the OAuth client secret and the personal device identifier.
- The Python virtual environment, caches and backup files.
- Old one-off scripts, experiments and credential diagnostics.

The project directory was cleaned up and replaced with this prepared version. The previous copy, including private settings and tokens, was backed up outside the project. No connection was made to the mower or the production openHAB installation during preparation.

## Missing original deployment files

- `/etc/systemd/system/navimow-openhab.service`: replaced with an adaptable example.
- openHAB item definitions: example definitions were created from the item names used by the poller.

The full virtual environment is not needed in the repository. SDK version 0.1.2 was identified from the available package metadata.

## License

GPL-3.0-only. The full license text is in `LICENSE`.

## Community testing wanted

1. Create a private `config.json` with your OAuth settings and verify login or token migration on the target system.
2. Test device discovery, automatic token refresh and updates to openHAB. Stop any previous service first to avoid two processes competing over refresh-token rotation.
3. Check the example service definition in your deployment.
4. Check the example Main UI page, including battery display, status color and item values.

Report your mower model, Python and openHAB versions, reproduction steps and sanitized logs through GitHub Issues. Do not include tokens, credentials or personal device identifiers.

Validation covered Python syntax, key failure cases using simulated responses, and checks that known private values were excluded. It does not replace testing against Navimow and openHAB.

## Local validation results

All nine offline regression tests passed. All Python files were checked for valid syntax. The files prepared for publication were scanned for known private values from the original copy; no matches were found.
