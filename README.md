# Show Schedule Builder

Show Schedule Builder extracts ride times for a selected list of riders from
HorseShowOffice.com, FoxVillage.com, or Equestrian-Hub.com, then generates an
Excel schedule that can be printed or shared with a barn team.

## Download and run

1. Open the latest GitHub release.
2. Download `Show Schedule Builder.zip`.
3. Unzip it.
4. Double-click `Show Schedule Builder.app`.
5. Paste the show URL, select riders, and click `Generate and Download Excel`.

The app runs locally on your Mac. It only needs internet access to read the
show software URLs that you paste into the page.

## macOS security message

Because this beta app is not yet signed and notarized by Apple, macOS may show
a message like:

`Apple could not verify "Show Schedule Builder" is free of malware.`

If that happens:

1. Click `Done`.
2. Control-click `Show Schedule Builder.app`.
3. Choose `Open`.
4. Choose `Open` again when macOS asks for confirmation.

If macOS still blocks the app, open `System Settings > Privacy & Security` and
choose `Open Anyway` for Show Schedule Builder.

As another fallback, Terminal can remove the download quarantine flag:

```sh
xattr -dr com.apple.quarantine "/path/to/Show Schedule Builder.app"
```
