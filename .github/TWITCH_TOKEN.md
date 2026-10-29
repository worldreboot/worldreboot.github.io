# Automatic Twitch token renewal

The `Renew Twitch token` workflow checks the app access token daily at 09:17 UTC.
It requests a replacement when the current token is invalid or has seven days
or less remaining, validates the replacement, commits it to `code` using the
existing `Bearer <token>` format, and requests a GitHub Pages rebuild.
Failed Twitch requests leave the existing file unchanged.

Add these repository secrets under Settings > Secrets and variables > Actions:

- `TWITCH_CLIENT_ID`: the Twitch app's client ID.
- `TWITCH_CLIENT_SECRET`: the same app's client secret.

The local `.twitch-credentials.json` file is ignored by Git and is only a way to
provide credentials during setup. The scheduled job reads GitHub secrets.
The generated access token continues to be published in `code` as requested.

To run immediately, open Actions > Renew Twitch token > Run workflow. Select
`force` to test renewal even when the current token does not need replacement.

Run the local checks with:

```powershell
python -m unittest discover -s .github/scripts -p 'test_*.py'
```

References: [Twitch app tokens](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow),
[token validation](https://dev.twitch.tv/docs/authentication/validate-tokens/),
[GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
and [GitHub Pages builds](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build).
