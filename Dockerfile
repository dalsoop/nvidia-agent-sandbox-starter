# syntax=docker/dockerfile:1
FROM ubuntu:24.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Python 3.12, pip, security/network inspection tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    ca-certificates \
    iptables \
    iproute2 \
    dnsutils \
    net-tools \
    iputils-ping \
    git \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Setup non-root sandbox user
ARG USERNAME=sandbox
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m -s /bin/bash ${USERNAME}

# Workspace configuration
WORKDIR /workspace
RUN chown -R ${USERNAME}:${USERNAME} /workspace

# Install common agent & evaluation dependencies into a dedicated venv
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv ${VIRTUAL_ENV} \
    && chown -R ${USERNAME}:${USERNAME} ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

# Pre-install baseline packages for fast bootstrapping
USER ${USERNAME}
RUN pip install --no-cache-dir --upgrade pip setuptools wheel pytest pyyaml pydantic httpx requests

USER ${USERNAME}
WORKDIR /workspace

CMD ["/bin/bash"]
