# Devpipe 基础镜像
# 用于 devpipe devspace 和 devpipe dashboard
#
# 包含环境：
#   - Python 3.12
#   - Node.js 20.x
#   - Git, SSH, 常用命令行工具
#   - GitHub CLI (gh)
#   - Claude Code CLI
#
# 构建命令（在 resources 目录执行，或通过 sync-docker-image.sh）：
#   docker build -t devpipe/devspace:latest resources/
#
# 镜像标签策略：
#   - latest: 始终指向最新构建
#   - <dockerfile-hash>: 基于 Dockerfile 内容的版本标签

FROM rockylinux:9

LABEL maintainer="devpipe"
LABEL description="Devpipe workspace base image for devspace and dashboard"

# ========================
# 系统基础配置
# ========================

COPY Rockylinux9-Base.repo /mnt/resources/Rockylinux9-Base.repo

# 配置 dnf 源（使用国内镜像）
RUN rm -f /etc/yum.repos.d/* \
    && cp /mnt/resources/Rockylinux9-Base.repo /etc/yum.repos.d/ \
    && dnf clean all \
    && dnf makecache

# 安装基础工具
RUN dnf install -y --allowerasing \
        # 编辑器和文本处理
        vim-enhanced jq tree \
        # 网络工具
        openssl net-tools bind-utils curl wget \
        # 系统工具
        lsof procps-ng which \
        # 压缩工具
        bzip2 xz tar gzip unzip \
        # 版本控制
        git \
        # Shell
        zsh \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 安装 GitHub CLI (gh)
RUN dnf install -y 'dnf-command(config-manager)' \n    && dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo \n    && dnf install -y gh \n    && dnf clean all \n    && rm -rf /var/cache/dnf

# 降低 SSH RSA 密钥长度限制
RUN update-crypto-policies --set LEGACY \n    && sed -i 's/^RequiredRSASize.*/RequiredRSASize 1024/' /etc/crypto-policies/back-ends/openssh.config

# ========================
# Node.js 20.x
# ========================

RUN dnf module enable -y nodejs:20 \
    && dnf install -y nodejs \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# ========================
# Python 3.12 + 常用包
# ========================

RUN dnf install -y python3.12 python3.12-pip \
    && alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 2 \
    && alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.12 2 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && pip3 install --no-cache-dir \
        flask==3.1.1 \
        openai==1.82.0 \
        requests==2.32.5 \
        pytest==9.0.1 \
        pytest-repeat==0.9.4 \
        allure-pytest==2.15.0 \
        allure-python-commons==2.15.0 \
        Jinja2==3.1.6 \
        selenium \
        anthropic \
        unidiff \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# ========================
# 安装 Claude Code CLI
# ========================

RUN npm install -g @anthropic-ai/claude-code

# ========================
# 创建开发用户
# ========================

ARG USER_NAME=devpipe
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd -g ${USER_GID} staff 2>/dev/null || true \
    && useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/zsh ${USER_NAME}

USER ${USER_NAME}
WORKDIR /home/${USER_NAME}

# ========================
# Zsh + Oh My Zsh + Powerlevel10k
# ========================

RUN git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git ~/.oh-my-zsh \
    && git clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
        ~/.oh-my-zsh/custom/themes/powerlevel10k

COPY --chown=${USER_NAME}:staff p10k.zsh /home/${USER_NAME}/.p10k.zsh
COPY --chown=${USER_NAME}:staff vimrc /home/${USER_NAME}/.vimrc

RUN cat > ~/.zshrc << 'ZSHRC_EOF'
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="powerlevel10k/powerlevel10k"
plugins=(git)
source $ZSH/oh-my-zsh.sh

alias claude='claude --plugin-dir $PWD/plugins/devpipe'
alias ll='ls -l'
alias la='ls -la'
alias gs='git status'
alias gd='git diff'
alias gl='git log --oneline -20'

[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
ZSHRC_EOF

# Claude Code 已通过 npm -g 安装，路径在 Node.js 全局 bin 中

# ========================
# 默认配置
# ========================

ARG WORKDIR=/home/${USER_NAME}
ENV TERM=xterm-256color

# 默认工作目录（可通过 docker run -w 覆盖）
WORKDIR ${WORKDIR}

# 默认入口点
ENTRYPOINT ["/bin/zsh"]
