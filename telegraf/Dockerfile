FROM telegraf:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    ntpstat && \
	rm -rf /var/lib/apt/lists/*

COPY scripts/ /etc/telegraf/scripts/
RUN chmod +x /etc/telegraf/scripts/*.sh