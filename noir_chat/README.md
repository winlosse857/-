# NOIR — Android chat prototype

Dark, modern Flutter app for topic-based community rooms.

## Included
- Dark UI with violet/cyan accents
- Topic rooms and recent chats
- Editable nickname
- Chat screen and message composer
- GitHub Actions workflow that builds an Android APK

## Important
This is a **local UI prototype**. Messages are held in memory and are not delivered to other devices. A real multi-user chat needs a backend (for example Supabase Realtime or Firebase), authentication, database access rules, moderation, and privacy rules. No API keys or credentials are included.

## Build locally
Install Flutter and the Android SDK, then run:
```bash
cd noir_chat
flutter pub get
flutter create --platforms=android --org com.noir --project-name noir_chat /tmp/noir_scaffold
cp -R /tmp/noir_scaffold/android ./android
flutter build apk --release
```
APK output: `build/app/outputs/flutter-apk/app-release.apk`.

## GitHub Actions
Push changes under `noir_chat/**` or manually run **Build NOIR Android APK**. Download the `noir-android-apk` artifact from the workflow run.
