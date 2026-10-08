#!/bin/sh
# Renders /etc/nginx/realip.conf from TRUSTED_PROXY_CIDRS / REAL_IP_HEADER.
# Runs from /docker-entrypoint.d/ at container start (and once at build time with
# empty env so the include always exists).
#
# Secure default: no trusted proxies -> no realip directives -> nginx uses the TCP
# peer address and ignores client-supplied IP/proto headers.
set -eu

OUT="${REALIP_CONF_PATH:-/etc/nginx/realip.conf}"
CIDRS="${TRUSTED_PROXY_CIDRS:-}"
HEADER_IN="${REAL_IP_HEADER:-X-Forwarded-For}"

fail() { echo "[realip] ERROR: $*" >&2; exit 1; }

# Validate + canonicalise the header name (allowlist only).
case "$(printf '%s' "$HEADER_IN" | tr '[:upper:]' '[:lower:]')" in
    x-forwarded-for) HEADER="X-Forwarded-For" ;;
    x-real-ip)       HEADER="X-Real-IP" ;;
    cf-connecting-ip) HEADER="CF-Connecting-IP" ;;
    true-client-ip)  HEADER="True-Client-IP" ;;
    *) fail "REAL_IP_HEADER='$HEADER_IN' is not allowed (use X-Forwarded-For, X-Real-IP, CF-Connecting-IP or True-Client-IP)" ;;
esac

# Returns 0 if $1 is a syntactically valid IPv4 or IPv6 address.
valid_ip() {
    awk -v a="$1" '
    function v4(x,  n,p,i) {
        n = split(x, p, ".")
        if (n != 4) return 0
        for (i = 1; i <= 4; i++) {
            if (p[i] !~ /^[0-9]+$/ || length(p[i]) > 3 || p[i] + 0 > 255) return 0
        }
        return 1
    }
    function v6(x,  t,dbl,n,p,i,groups) {
        if (x !~ /^[0-9A-Fa-f:]+$/ || index(x, ":") == 0) return 0
        if (index(x, ":::") > 0) return 0
        t = x; dbl = gsub(/::/, "", t)
        if (dbl > 1) return 0
        if (x ~ /^:[^:]/ || x ~ /[^:]:$/) return 0
        n = split(x, p, ":"); groups = 0
        for (i = 1; i <= n; i++) {
            if (p[i] == "") continue
            if (length(p[i]) > 4) return 0
            groups++
        }
        if (dbl == 0) return (groups == 8 && n == 8)
        return (groups <= 7)
    }
    BEGIN { exit !(v4(a) || v6(a)) }'
}

LINES=""
set -f
for tok in $(printf '%s' "$CIDRS" | tr ',' ' '); do
    addr="${tok%%/*}"
    case "$tok" in
        */*) prefix="${tok#*/}" ;;
        *)   prefix="" ;;
    esac
    case "$prefix" in */*) fail "invalid entry '$tok' in TRUSTED_PROXY_CIDRS" ;; esac
    valid_ip "$addr" || fail "invalid IP/CIDR '$tok' in TRUSTED_PROXY_CIDRS (expected e.g. 10.0.0.0/8 or 2001:db8::/32)"
    case "$addr" in *:*) max=128 ;; *) max=32 ;; esac
    if [ -n "$prefix" ]; then
        case "$prefix" in
            ''|*[!0-9]*) fail "invalid prefix length in '$tok'" ;;
        esac
        [ "$prefix" -le "$max" ] || fail "prefix length out of range in '$tok'"
        [ "$prefix" -gt 0 ] || fail "'$tok' would trust every address and re-enable IP spoofing; list only proxies you control"
    fi
    LINES="$LINES$tok
"
done
set +f

TMP="$OUT.tmp"
{
    echo "# Generated at container start by docker-entrypoint-realip.sh - do not edit."
    echo "# Trusted peers: ${CIDRS:-none (secure default: TCP peer address is used)}"
    if [ -n "$LINES" ]; then
        printf '%s' "$LINES" | while IFS= read -r c; do
            [ -n "$c" ] && echo "set_real_ip_from $c;"
        done
        echo "real_ip_header $HEADER;"
        echo "real_ip_recursive on;"
    fi
    echo "# 1 when the connecting TCP peer is a trusted proxy (so its X-Forwarded-Proto,"
    echo "# CF-* headers etc. may be believed); 0 otherwise."
    echo 'geo $realip_remote_addr $trusted_peer {'
    echo "    default 0;"
    if [ -n "$LINES" ]; then
        printf '%s' "$LINES" | while IFS= read -r c; do
            [ -n "$c" ] && echo "    $c 1;"
        done
    fi
    echo "}"
} > "$TMP"
mv "$TMP" "$OUT"

if [ -n "$LINES" ]; then
    echo "[realip] Trusting proxies: $(printf '%s' "$LINES" | tr '\n' ' ')- client IP from $HEADER"
else
    echo "[realip] No trusted proxies configured: using the TCP peer address and ignoring client-supplied IP/proto headers"
fi
