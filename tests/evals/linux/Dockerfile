# The Linux eval image: Ubuntu 24.04 with git, jq, python3, ps, flock and curl, one unprivileged user, and the pinned
# Herdr TUI, Herdr Core and moshi-hook in that user's ~/.local/bin, each checked by sha256 (pins.txt). No systemd:
# install.sh takes its flock path here. The checkout under test is copied in at run time by run.sh, never baked in.
FROM ubuntu:24.04
# The user is evaluser, a name no message or path of the product carries, so the records' user-name scrub touches nothing else.
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      ca-certificates curl git jq python3 procps util-linux >/dev/null && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1001 -s /bin/bash evaluser
USER evaluser
WORKDIR /home/evaluser
ENV HOME=/home/evaluser PATH=/home/evaluser/.local/bin:/usr/local/bin:/usr/bin:/bin SHELL=/bin/bash TERM=xterm-256color LANG=C.UTF-8
COPY --chown=evaluser:evaluser pins.txt install-pinned.sh /home/evaluser/.local/share/stampede-eval/
RUN bash /home/evaluser/.local/share/stampede-eval/install-pinned.sh
