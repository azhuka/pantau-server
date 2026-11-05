# Pantau NOC Audit Hook: Sinkronisasi instan riwayat perintah shell ke disk
export HISTTIMEFORMAT="%Y-%m-%d %H:%M:%S "
shopt -s histappend 2>/dev/null || true
export PROMPT_COMMAND="history -a${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
