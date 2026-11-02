#!/usr/bin/env bash
# Match the Ubuntu worker already exercised by the Linux preparation trial.
set -euo pipefail
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 && $(dpkg --print-architecture) == amd64 ]]
VERSION=$(tr -d '[:space:]' < api/r/.R-version)
[[ "$VERSION" == 4.6.1 ]] # Update the installer checksum deliberately with R.
INSTALLER="${RUNNER_TEMP:?}/r-${VERSION}_1_amd64.deb"
curl --fail --location --retry 2 --output "$INSTALLER" \
  "https://cdn.posit.co/r/ubuntu-2404/pkgs/r-${VERSION}_1_amd64.deb"
echo "5af816371126c8e5895600de035153cd3a64b12f4beb43f291ee34bf24f8fd2d  $INSTALLER" | sha256sum --check -
sudo apt-get update
sudo apt-get install -y --no-install-recommends "$INSTALLER" build-essential gfortran pkg-config \
  libcurl4-openssl-dev libssl-dev libxml2-dev libicu-dev libblas-dev liblapack-dev
"/opt/R/$VERSION/bin/Rscript" --vanilla -e 'stopifnot(as.character(getRversion()) == "4.6.1")'
