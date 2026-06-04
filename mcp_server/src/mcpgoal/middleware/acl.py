import ipaddress
from typing import Optional

from mcpgoal.config import ServerConfig, ToolACL


def _ip_matches(ip_str: str, entry: str) -> bool:
    try:
        network = ipaddress.ip_network(entry, strict=False)
        return ipaddress.ip_address(ip_str) in network
    except ValueError:
        return ip_str.lower() == entry.lower()


def check_access(tool_name: str, client_ip: Optional[str], config: ServerConfig) -> bool:
    if client_ip is None:
        return True

    acl: Optional[ToolACL] = config.tools.get(tool_name)
    if acl is None:
        return False

    has_whitelist = len(acl.whitelist) > 0
    has_blacklist = len(acl.blacklist) > 0
    blacklist_has_wildcard = "*" in acl.blacklist

    if has_whitelist:
        if any(_ip_matches(client_ip, entry) for entry in acl.whitelist):
            return True
        if blacklist_has_wildcard:
            return False
        return False

    if blacklist_has_wildcard:
        return False

    if has_blacklist:
        return not any(_ip_matches(client_ip, entry) for entry in acl.blacklist)

    return True
