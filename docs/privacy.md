# Privacy policy

Effective 24 November 2026.

This policy covers the Intervals Coach MCP app: a privately run copy of the
open-source [intervals-icu-mcp](https://github.com/krazykev300/intervals-icu-mcp)
server, which connects an AI assistant (Claude) to Intervals.icu. One person
runs it, for themselves and a few friends they invite. It is not a commercial
service, and nobody can sign up without being invited.

## What the app accesses

When you connect, Intervals.icu asks you to approve the access the app needs:

- **Activities:** read your activities, streams and curves, and log sessions
  you ask it to log.
- **Wellness:** read your wellness data and update it when you ask.
- **Calendar:** read your planned workouts and events, and create, change or
  delete them when you approve a change in chat.
- **Workout library:** read your workouts.
- **Settings:** read your profile, sport settings (FTP, thresholds, zones) and
  gear.

The app reads this data from Intervals.icu at the moment the assistant needs
it. It does not copy your training history anywhere.

## What the app stores

- **Your sign-in.** The access token Intervals.icu issues when you approve the
  app, plus your athlete id and name. The token is encrypted at rest on the
  server and used only to call Intervals.icu for you.
- **Short-lived caches.** A few derived values (for example your timezone)
  are kept in memory while the server runs, so repeated requests are faster.
  They are keyed to your sign-in, so other users cannot see them, and they are
  gone when the server restarts.
- **Request logs.** The server's web log records the time, path and status of
  each request. It does not record your training data, tool inputs or tokens.

The app has no database of your activities, wellness or calendar. Intervals.icu
remains the record.

## Where your data goes

- **To the AI assistant you connect it to.** The data the app reads is
  returned to your own assistant conversation, for example in Claude. That
  provider's own privacy terms apply to your conversations. The app does not
  send your data to any other AI provider or third party.
- **Nowhere else.** Your data is never sold, shared for advertising, or used to
  train models by this app.
- **Garmin data.** Activities recorded on Garmin devices are attributed to
  Garmin, as Intervals.icu's API terms require.

## Who can see it

The person who runs the server administers the machine it runs on. They can
technically read the server's stored tokens and logs, and they commit to using
them only to keep the service running. Other users of the same server cannot
see your data.

## Your control

- **Disconnect at any time.** Remove the app in Intervals.icu under Settings →
  Apps, or ask the person who runs the server to remove you. Either one ends
  the app's access immediately.
- **Deletion.** When you are removed, your stored token is deleted. Nothing
  else about you is kept beyond the request logs, which are routinely rotated.
- **Questions.** Contact the person who invited you, or open an issue on the
  [GitHub repository](https://github.com/krazykev300/intervals-icu-mcp/issues).
  Do not put personal or health details in a public issue.

## Changes

If this policy changes, the new version will be published at this address with
a new effective date, and current users will be told directly.
