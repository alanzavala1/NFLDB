#!/usr/bin/env bash
# Preserve the preview-only entry point for existing local commands.
export SERVICE=nfldb-native-preview
exec bash "$(dirname "$0")/native-deploy.sh"
