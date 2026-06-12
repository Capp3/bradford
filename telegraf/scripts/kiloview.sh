#!/bin/sh
# Poll a Kiloview N5/N6 NDI unit and emit one JSON object on stdout for Telegraf.
#
# Why this script exists: the device's auth token is returned in the login
# response BODY (not as a Set-Cookie header), so Telegraf's built-in
# cookie_auth_url cannot capture it. We log in, read the token, then send it
# back as the "token" cookie (the documented mechanism). The token is cached
# per-unit and only refreshed when the session is rejected.
#
# Offline/bad-credential units simply emit {"up":0} and exit 0, so a down unit
# never aborts the Telegraf agent.
#
# Usage: kiloview.sh <host> <unit-tag>
set -u

host="${1:?host required}"
unit="${2:?unit tag required}"
user="${NDI_API_USER:-}"
pass="${NDI_API_PASS:-}"
base="https://${host}/api"
cache="/tmp/kv_token_${unit}"

down() { echo '{"up":0}'; exit 0; }

authorize() {
  curl -sk -m 5 "${base}/user/authorize.json?user=${user}&password=${pass}" 2>/dev/null \
    | jq -r 'if .result=="ok" then .data.token else empty end' 2>/dev/null
}

call() { curl -sk -m 5 -b "token=$1" "${base}/$2" 2>/dev/null; }

token=""
[ -f "$cache" ] && token="$(cat "$cache" 2>/dev/null)"

status="$(call "$token" "decoder/current/status.json")"
case "$status" in
  *'"result":"ok"'*) : ;;                 # cached token still valid
  *)
    token="$(authorize)"
    [ -z "$token" ] && down               # offline or bad credentials
    printf '%s' "$token" > "$cache"
    status="$(call "$token" "decoder/current/status.json")"
    case "$status" in *'"result":"ok"'*) : ;; *) down ;; esac
    ;;
esac

info="$(call "$token" "sys/server_info.json")"

# Some firmware embeds a raw newline inside string values (e.g. serial_number),
# which is invalid JSON and makes jq reject the whole payload. Strip all C0
# control characters before parsing; objects stay self-delimiting via the space.
info_part=""
case "$info" in *'"result":"ok"'*) info_part="$info" ;; esac

# Base the metric on the decoder status, then add only the useful system fields
# from server_info (avoids server_info's "name"=web-URL clobbering the NDI source
# name, and drops redundant fields).
printf '%s %s' "$status" "$info_part" \
  | tr -d '\000-\037' \
  | jq -cs '
      ((.[0].data) // {}) as $s
      | ((.[1].data) // {}) as $i
      | $s + {
          cpu_cores: $i.cpu_cores,
          cpu_payload: $i.cpu_payload,
          mem_used: $i.mem_used,
          mem_total: $i.mem_total,
          persis: $i.persis,
          start_time: $i.start_time,
          online: (if $s.online then 1 else 0 end),
          is_full: (if $s.isFull then 1 else 0 end),
          up: 1
        }
      | del(.isFull)
      | with_entries(select(.value != null))
    ' 2>/dev/null
