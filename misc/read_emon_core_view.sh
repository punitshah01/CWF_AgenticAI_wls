#!/usr/bin/env bash
# misc/read_emon_core_view.sh — Extract data from __mpp_core_view_summary.csv
# Usage: bash misc/read_emon_core_view.sh <emon_csv_file>

emon_logfile="$1"
[[ -z "$emon_logfile" || ! -f "$emon_logfile" ]] && \
    { echo "Usage: $0 <emon_csv>" >&2; exit 1; }

emon_data=""
{
    read
    while IFS=, read -r line; do
        emon_data+=$(echo "$line" | awk -F"," '{
            for(i=2;i<=NF;i++) {
                if ($i+0 >= 1) printf "%0.2f,", $i
                else           printf "%.5f,",  $i
            }
        }')
    done
} < "$emon_logfile"
echo "${emon_data%,}"
