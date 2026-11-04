# Pantau NOC Audit: Pencatatan waktu riwayat perintah shell & sinkronisasi instan
export HISTTIMEFORMAT="%Y-%m-%d %H:%M:%S "
export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"
