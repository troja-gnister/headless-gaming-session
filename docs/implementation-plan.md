# Implementation plan

1. Add stdlib Python controller, socket client, clickable Sway status bar,
   configuration templates, Steam shortcut helper, and meaningful tests.
2. Add deployment/rollback tools with file backups, dependency manifest,
   configuration rendering, and a dry-run plan. Add usage/recovery documentation.
3. Validate locally before installing. Install desktop dependency, back up and
   deploy to the current user. Stop Steam before updating shortcuts.vdf.
4. Test all resolutions, both mode transitions and unchanged capture processes.
   Verify the Steam shortcut's exact command inside the Flatpak. Leave Gaming
   Mode running and report any remaining client-side confirmation.
