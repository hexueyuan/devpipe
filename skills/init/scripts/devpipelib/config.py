"""devpipe.yml 配置解析（不依赖 PyYAML）"""

import os
from dataclasses import dataclass, field
from typing import Optional

from .shell import ConfigError


@dataclass
class PortMapping:
    """端口映射"""
    host_port: int
    container_port: int


@dataclass
class MountMapping:
    """额外挂载映射"""
    host_path: str       # 相对于 worktree 的宿主机路径
    container_path: str  # 相对于容器工作空间的路径


@dataclass
class DevpipeConfig:
    """项目级 devpipe 配置"""
    ports: list[PortMapping] = field(default_factory=list)
    mounts: list[MountMapping] = field(default_factory=list)
    docs_dir: Optional[str] = None  # 文档存放目录，相对于仓库根目录，默认 .devpipe/docs

    @classmethod
    def load(cls, repo_root: str) -> "DevpipeConfig":
        """
        从 {repo_root}/.devpipe/devpipe.yml 加载配置。
        文件不存在时返回空配置。
        """
        path = os.path.join(repo_root, ".devpipe", "devpipe.yml")
        if not os.path.isfile(path):
            return cls()

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            raise ConfigError(f"无法读取 {path}: {e}")

        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: str) -> "DevpipeConfig":
        """
        极简 YAML 解析器。

        只支持：
          - 顶层 key: scalar_value
          - 顶层 key: 后跟缩进的 - value 列表
          - # 注释和空行
        """
        ports: list[PortMapping] = []
        mounts: list[MountMapping] = []
        docs_dir: Optional[str] = None
        current_key: Optional[str] = None

        for lineno, line in enumerate(raw.splitlines(), start=1):
            stripped = line.strip()

            # 空行或注释
            if not stripped or stripped.startswith("#"):
                continue

            # 列表项：  - value
            if stripped.startswith("- "):
                if current_key is None:
                    raise ConfigError(f"第 {lineno} 行：列表项出现在 key 之前")
                value = stripped[2:].strip()
                # 去掉行内注释
                if "#" in value:
                    value = value[:value.index("#")].strip()
                if current_key == "ports":
                    ports.append(_parse_port(value, lineno))
                elif current_key == "mounts":
                    mounts.append(_parse_mount(value, lineno))
                continue

            # 顶层 key: value
            if ":" in stripped:
                key, _, rest = stripped.partition(":")
                key = key.strip()
                rest = rest.strip()
                # 去掉行内注释
                if rest and "#" in rest:
                    rest = rest[:rest.index("#")].strip()

                if rest:
                    # scalar value
                    if key == "docs_dir":
                        docs_dir = rest
                    current_key = None
                else:
                    current_key = key
                continue

            raise ConfigError(f"第 {lineno} 行：无法解析 '{stripped}'")

        return cls(ports=ports, mounts=mounts, docs_dir=docs_dir)

    def docker_port_args(self) -> list[str]:
        """返回 docker run 的 -p 参数列表"""
        args: list[str] = []
        for pm in self.ports:
            args.extend(["-p", f"{pm.host_port}:{pm.container_port}"])
        return args

    def docker_mount_args(self, worktree_path: str, container_workspace: str) -> list[str]:
        """返回 docker run 的额外 -v 挂载参数列表"""
        args: list[str] = []
        for mm in self.mounts:
            host = os.path.join(worktree_path, mm.host_path)
            container = os.path.join(container_workspace, mm.container_path)
            args.extend(["-v", f"{host}:{container}"])
        return args

    def get_docs_base_dir(self, repo_root: str) -> str:
        """
        获取文档存放的基础目录（绝对路径）。

        Args:
            repo_root: 仓库根目录

        Returns:
            绝对路径，默认为 {repo_root}/.devpipe/docs
        """
        if self.docs_dir:
            # 支持相对路径和绝对路径
            if os.path.isabs(self.docs_dir):
                return self.docs_dir
            return os.path.join(repo_root, self.docs_dir)
        return os.path.join(repo_root, ".devpipe", "docs")


def _parse_port(value: str, lineno: int) -> PortMapping:
    """
    解析端口值。支持：
      - 5173          → PortMapping(5173, 5173)
      - 8080:3000     → PortMapping(8080, 3000)
    """
    value = value.strip()
    if ":" in value:
        parts = value.split(":", 1)
        try:
            return PortMapping(int(parts[0]), int(parts[1]))
        except ValueError:
            raise ConfigError(f"第 {lineno} 行：无效的端口映射 '{value}'")
    else:
        try:
            port = int(value)
            return PortMapping(port, port)
        except ValueError:
            raise ConfigError(f"第 {lineno} 行：无效的端口号 '{value}'")


def _parse_mount(value: str, lineno: int) -> MountMapping:
    """
    解析挂载值。支持：
      - public              → MountMapping("public", "public")
      - src/assets:dist/assets → MountMapping("src/assets", "dist/assets")
    """
    value = value.strip()
    if not value:
        raise ConfigError(f"第 {lineno} 行：挂载路径不能为空")
    if ":" in value:
        parts = value.split(":", 1)
        host = parts[0].strip()
        container = parts[1].strip()
        if not host or not container:
            raise ConfigError(f"第 {lineno} 行：无效的挂载映射 '{value}'")
        return MountMapping(host, container)
    return MountMapping(value, value)
