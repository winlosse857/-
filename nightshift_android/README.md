# NIGHTSHIFT — Android neon maze game

A small offline Flutter arcade game with a dark cyberpunk look.

## Play
- Tap **НАЧАТЬ ИГРУ**.
- Use the arrow buttons to move through the maze.
- Collect cyan energy orbs to increase your score and extend the timer.
- Reach the purple exit before your energy runs out.

## Build an APK
The GitHub Actions workflow **Build Android APK** generates a release APK automatically when the game files change. Open the repository's **Actions** tab, select the latest successful run, and download the `nightshift-release-apk` artifact.

To build locally, install Flutter and Android SDK, then:
```sh
cd nightshift_android
flutter create --platforms=android .
flutter pub get
flutter build apk --release
```
The APK is created at `build/app/outputs/flutter-apk/app-release.apk`.

## Project
The game is intentionally dependency-light and keeps the game logic and neon maze drawing in `lib/main.dart`.
