#!/usr/bin/env python
import sys
import yaml

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    log,
    relation_get,
    relation_ids,
    related_units,
    status_set,
    relation_set,
    local_unit,
    open_port,
    close_port,
)

import contrail_analytics_utils as utils
import common_utils
import docker_utils


hooks = Hooks()
config = config()


@hooks.hook("install.real")
def install():
    status_set("maintenance", "Installing...")

    # TODO: try to remove this call
    common_utils.fix_hostname()

    docker_utils.install()
    utils.update_charm_status()
    # NOTE: do not open port until haproxy can fail
    # https://bugs.launchpad.net/charm-haproxy/+bug/1792939
    #open_port(8081, "TCP")


@hooks.hook("config-changed")
def config_changed():
    # ingress-address and private-address (legacy) values are automatically
    # populated by Juju based on endpoint bindings, the code below is for
    # control-network config-based approach
    rnames = ("contrail-analytics", "contrail-analyticsdb",
              "analytics-cluster", "http-services")
    if config.changed("control-network") and config("control-network"):
        settings = {'private-address': common_utils.get_ip()}
        for rname in rnames:
            for rid in relation_ids(rname):
                relation_set(relation_id=rid, relation_settings=settings)
    elif config.changed("control-network") and not config("control-network"):
        for rname in rnames:
            ip = common_utils.get_ip(endpoint=rname)
            settings = {"private-address": ip}
            for rid in relation_ids(rname):
                relation_set(relation_id=rid, relation_settings=settings)

    docker_utils.config_changed()
    utils.update_charm_status()


def _value_changed(rel_data, rel_key, cfg_key):
    if rel_key not in rel_data:
        # data is absent in relation. it means that remote charm doesn't
        # send it due to lack of information
        return False
    value = rel_data[rel_key]
    if value is not None and value != config.get(cfg_key):
        config[cfg_key] = value
        return True
    elif value is None and config.get(cfg_key) is not None:
        config.pop(cfg_key, None)
        return True
    return False


@hooks.hook("contrail-analytics-relation-joined")
def contrail_analytics_joined():
    # ingress-address and private-address (legacy) are automatically set by
    # Juju based on endpoint bindings - this code is for compatibility with
    # contrail-network config based approach
    settings = {"private-address": common_utils.get_ip(
        endpoint='contrail-analytics')}
    relation_set(relation_settings=settings)


@hooks.hook("contrail-analytics-relation-changed")
def contrail_analytics_changed():
    data = relation_get()
    changed = False
    changed |= _value_changed(data, "api-vip", "api_vip")
    changed |= _value_changed(data, "auth-mode", "auth_mode")
    changed |= _value_changed(data, "auth-info", "auth_info")
    changed |= _value_changed(data, "orchestrator-info", "orchestrator_info")
    changed |= _value_changed(data, "ssl-enabled", "ssl_enabled")
    changed |= _value_changed(data, "rabbitmq_hosts", "rabbitmq_hosts")
    config.save()
    # TODO: handle changing of all values
    # TODO: set error if orchestrator is changing and container was started
    if changed:
        utils.update_charm_status()
        _notify_proxy_services()


@hooks.hook("contrail-analytics-relation-departed")
def contrail_analytics_departed():
    units = [unit for rid in relation_ids("contrail-controller")
                  for unit in related_units(rid)]
    if not units:
        for key in ["api_vip", "auth_info", "auth_mode", "orchestrator_info",
                    "ssl_enabled", "rabbitmq_hosts"]:
            config.pop(key, None)
    config.save()
    utils.update_charm_status()
    _notify_proxy_services()


@hooks.hook("contrail-analyticsdb-relation-joined")
def contrail_analyticsdb_joined():
    settings = {"private-address": common_utils.get_ip(),
                'unit-type': 'analytics'}
    relation_set(relation_settings=settings)


@hooks.hook("contrail-analyticsdb-relation-changed")
def contrail_analyticsdb_changed():
    utils.update_charm_status()


@hooks.hook("contrail-analyticsdb-relation-departed")
def contrail_analyticsdb_departed():
    utils.update_charm_status()


@hooks.hook("analytics-cluster-relation-joined")
def analytics_cluster_joined():
    settings = {"private-address": common_utils.get_ip()}
    relation_set(relation_settings=settings)

    utils.update_charm_status()


@hooks.hook("update-status")
def update_status():
    utils.update_charm_status()


@hooks.hook("upgrade-charm")
def upgrade_charm():
    utils.update_charm_status()


def _notify_proxy_services():
    for rid in relation_ids("http-services"):
        if related_units(rid):
            http_services_joined(rid)


def _http_services(vip):
    name = local_unit().replace("/", "-")
    addr = common_utils.get_ip()
    return [{"service_name": "contrail-analytics-api",
             "service_host": vip,
             "service_port": 8081,
             "service_options": ["option nolinger", "balance roundrobin"],
             "servers": [[name, addr, 8081, "check inter 2000 rise 2 fall 3"]]
            }]


@hooks.hook("http-services-relation-joined")
def http_services_joined(rel_id=None):
    vip = config.get("api_vip")
    func = close_port if vip else open_port
    for port in ["8081"]:
        try:
            func(port, "TCP")
        except Exception:
            pass
    data = list() if not vip else _http_services(str(vip))
    relation_set(relation_id=rel_id,
                 services=yaml.dump(data))


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))


if __name__ == "__main__":
    main()
