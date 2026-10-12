# Dolbagram — Android messenger MVP

Dolbagram is an Android Flutter app with a Telegram-inspired interface and a Supabase backend.

## Current features
- Email/password registration and sign-in through Supabase Auth
- NOIR-style user identifiers generated for app accounts
- Public group list and joining groups
- Persistent group messages stored in PostgreSQL
- Live message updates through Supabase Realtime
- Row Level Security policies restricting message access to group members
- Android APK build through GitHub Actions

## Current limitations
This is an early MVP, not a complete Telegram replacement yet. Direct/private chats, attachments, voice/video calls, push notifications, read receipts, message editing/deletion UI, account recovery UI, and end-to-end encryption are not implemented. The Telegram bot's existing NOIR identities are not yet linked to app accounts. Do not use it for sensitive conversations until security and multi-device tests are completed.

## Build
The Android build is automated by **Build Dolbagram Android APK**. Open the repository's Actions tab, select the latest successful run, and download the `dolbagram-android-apk` artifact. GitHub provides the APK inside a ZIP archive.

## Backend
The Supabase schema and migrations are in `supabase/migrations`. The app uses a publishable client key only; never put a Supabase service-role key or Telegram bot token in the Flutter app.
