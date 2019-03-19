#!/usr/bin/env python

import sys

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    log,
    relation_get,
    related_units,
    relation_ids,
    status_set,
    relation_set,
)

import contrail_analyticsdb_utils as utils
import common_utils
import docker_utils


hooks = Hooks()
config = config()


@hooks.hook("install.real")
def install():
    status_set('maintenance', 'Installing...')

    # TODO: try to remove this call
    common_utils.fix_hostname()

    docker_utils.install()
    utils.update_charm_status()


@hooks.hook("config-changed")
def config_changed():
    # ingress-address and private-address (legacy) values are automatically
    # populated by Juju based on endpoint bindings, the code below is for
    # control-network config-based approach
    rnames = ("contrail-analyticsdb", "analyticsdb-cluster")
    if config.changed("control-network"):
        settings = {'private-address': common_utils.get_ip()}
        for rname in rnames:
            for rid in relation_ids(rname):
                relation_set(relation_id=rid, relation_settings=settings)
    elif (config.changed("control-network")
          and not config.get("control-network")):
        for rname in rnames:
            ip = common_utils.get_ip(endpoint=rname)
            settings = {"private-address": ip}
            for rid in relation_ids(rname):
                relation_set(relation_id=rid, relation_settings=settings)

    docker_utils.config_changed()
    utils.update_charm_status()


@hooks.hook("contrail-analyticsdb-relation-joined")
def analyticsdb_joined():
    settings = {
        'private-address': common_utils.get_ip(
            endpoint='contrail-analyticsdb')
    }
    relation_set(relation_settings=settings)


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


@hooks.hook("contrail-analyticsdb-relation-changed")
def analyticsdb_changed():
    data = relation_get()
    changed = False
    changed |= _value_changed(data, "auth-info", "auth_info")
    changed |= _value_changed(data, "orchestrator-info", "orchestrator_info")
    changed |= _value_changed(data, "ssl-enabled", "ssl_enabled")
    # TODO: handle changing of all values
    # TODO: set error if orchestrator is changing and container was started
    if changed:
        utils.update_charm_status()


@hooks.hook("contrail-analyticsdb-relation-departed")
def analyticsdb_departed():
    units = [unit for rid in relation_ids("contrail-controller")
                  for unit in related_units(rid)]
    if not units:
        for key in ["auth_info", "orchestrator_info", "ssl_enabled"]:
            config.pop(key, None)
    utils.update_charm_status()


@hooks.hook("analyticsdb-cluster-relation-joined")
def analyticsdb_cluster_joined():
    settings = {
        'private-address': common_utils.get_ip(
            endpoint='analyticsdb-cluster'
        )}
    relation_set(relation_settings=settings)


@hooks.hook("update-status")
def update_status():
    utils.update_charm_status()


@hooks.hook("upgrade-charm")
def upgrade_charm():
    utils.update_charm_status()


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))


if __name__ == "__main__":
    main()
