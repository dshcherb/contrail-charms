#!/usr/bin/env python

import json
import sys

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    log,
    is_leader,
    relation_get,
    relation_ids,
    relation_set,
    relation_id,
    related_units,
    status_set,
)

hooks = Hooks()
config = config()


def update_relations(rid=None):
    settings = {
        "auth-info": config.get("auth_info")
    }
    for rid in ([rid] if rid else relation_ids("contrail-auth")):
        relation_set(relation_id=rid, relation_settings=settings)


@hooks.hook("config-changed")
def config_changed():
    if is_leader():
        update_relations()
    update_status()


@hooks.hook("contrail-auth-relation-joined")
def contrail_auth_joined():
    if is_leader():
        update_relations(rid=relation_id())
    update_status()


@hooks.hook("identity-admin-relation-changed")
def identity_admin_changed():
    ip = relation_get("service_hostname")
    if ip:
        auth_info = {
            "keystone_protocol": relation_get("service_protocol"),
            "keystone_ip": ip,
            "keystone_public_port": relation_get("service_port"),
            "keystone_admin_user": relation_get("service_username"),
            "keystone_admin_password": relation_get("service_password"),
            "keystone_admin_tenant": relation_get("service_tenant_name"),
            "keystone_region": relation_get("service_region")}
        # TODO: read version from keystone also and use it everywhere
        auth_info = json.dumps(auth_info)
        config["auth_info"] = auth_info
    else:
        config.pop("auth_info", None)

    if is_leader():
        update_relations()
    update_status()


@hooks.hook("identity-admin-relation-departed")
def identity_admin_departed():
    count = 0
    for rid in relation_ids("identity-admin"):
        count += len(related_units(rid))
    if count > 0:
        return
    config.pop("auth_info", None)

    if is_leader():
        update_relations()
    update_status()


@hooks.hook("update-status")
def update_status():
    auth_info = config.get("auth_info")
    if not auth_info:
        status_set('blocked', 'Missing relations: identity')
    else:
        status_set("active", "Unit ready")


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))


if __name__ == "__main__":
    main()
