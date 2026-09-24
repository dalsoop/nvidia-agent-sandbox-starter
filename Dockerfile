# Sandbox image for `openshell sandbox create --from .`
# OpenShell requires a non-root OCI USER; WORKDIR /sandbox selects the managed workspace.
# iproute2 and nftables are used by the OpenShell supervisor to build the sandbox
# network namespace (see NVIDIA/OpenShell examples/bring-your-own-container).
FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates iproute2 nftables \
    && rm -rf /var/lib/apt/lists/* \
    && userdel --remove ubuntu \
    && groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /bin/bash sandbox

COPY agent /opt/agent/agent
COPY skills /opt/agent/skills
# A .pth entry instead of ENV PYTHONPATH: `openshell sandbox exec` and
# `sandbox connect` sessions do not inherit the image's ENV.
RUN echo /opt/agent > /usr/lib/python3/dist-packages/nvidia-agent-sandbox-starter.pth

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /sandbox
USER sandbox
CMD ["python3", "-m", "agent", "--help"]
