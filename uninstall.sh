#!/usr/bin/bash
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$bundle_dir/deploy.py" --rollback "$@"
