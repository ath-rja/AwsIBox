import troposphere.servicediscovery  as srvd

from .common import *
from .shared import (Parameter, do_no_override, get_endvalue, get_expvalue,
    get_subvalue, auto_get_props, get_condition, add_obj)


class ServiceDiscoveryPublicDnsNamespace(srvd.PublicDnsNamespace):
    def setup(self):
        self.Description = 'Service Discovery'
        self.Name = Sub('find.' + cfg.HostedZoneNameEnv)


class SRVD_ServiceDiscoveryRES(object):
    def __init__(self, key):
        # Resources
        R_PublicDnsNamespace = ServiceDiscoveryPublicDnsNamespace('PublicDnsNamespace')
        R_PublicDnsNamespace.setup()

        add_obj([
            R_PublicDnsNamespace,
        ])

        # Outputs
        O_PublicDnsNamespace = Output('ServiceDiscoveryPublicDnsNamespaceId')
        O_PublicDnsNamespace.Value = Ref('PublicDnsNamespace')
        O_PublicDnsNamespace.Export = Export('ServiceDiscoveryPublicDnsNamespaceId')

        add_obj([
            O_PublicDnsNamespace,
        ])
