# Pantau NOC Audit Hook: Sinkronisasi instan & audit real-time perintah shell
__pantau_prompt_audit() {
    local h
    h=$(history 1 2>/dev/null)
    [ -z "$h" ] && return
    h="${h#"${h%%[! ]*}"}"
    h="${h#*[0-9] }"
    h="${h#"${h%%[! ]*}"}"
    local cmd
    if [[ "$h" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]][0-9]{2}:[0-9]{2}:[0-9]{2}[[:space:]]+(.*)$ ]]; then
        cmd="${BASH_REMATCH[1]}"
    else
        cmd="$h"
    fi
    [ -z "$cmd" ] && return
    if [ "$cmd" != "$__PANTAU_LAST_CMD" ]; then
        __PANTAU_LAST_CMD="$cmd"
        case "$cmd" in
            *__pantau*|*logger*|"history -a"*) ;;
            *)
                local t
                t=$(tty 2>/dev/null || echo "lokal")
                t=${t#/dev/}
                logger -t pantau-shell -p auth.notice -- "[USER=$USER] [PWD=$PWD] [TTY=$t] CMD: $cmd" 2>/dev/null || true
                ;;
        esac
    fi
    history -a 2>/dev/null || true
}

if [ -n "$BASH_VERSION" ]; then
    export HISTTIMEFORMAT="%Y-%m-%d %H:%M:%S "
    shopt -s histappend 2>/dev/null || true
    case "$PROMPT_COMMAND" in
        *__pantau_prompt_audit*) ;;
        *) export PROMPT_COMMAND="__pantau_prompt_audit${PROMPT_COMMAND:+; $PROMPT_COMMAND}" ;;
    esac
fi
