import troposphere.route53 as r53

from .common import *
from .shared import (Parameter, do_no_override, get_endvalue, get_expvalue,
    get_subvalue, auto_get_props, get_condition, add_obj)


# S - ROUTE53 #
class R53RecordSet(r53.RecordSetType):
    def setup(self):
        pass


class R53RecordSetZoneExternal(R53RecordSet):
    def setup(self):
        super(R53RecordSetZoneExternal, self).setup()
        self.HostedZoneId = get_expvalue('HostedZoneIdEnv')
        self.Name = Sub('${AWS::StackName}.${EnvRole}.' + cfg.HostedZoneNameRegionEnv)  # Ex. prt-a-d.client-portal.eu-west-1.dev..


class R53RecordSetZoneInternal(R53RecordSet):
    def setup(self):
        super(R53RecordSetZoneInternal, self).setup()
        self.HostedZoneId = get_expvalue('HostedZoneIdPrivate')
        self.Name = Sub('${AWS::StackName}.${EnvRole}.' + cfg.HostedZoneNamePrivate)  # Ex. prt-a-d.client-portal.internal..


class R53RecordSetCloudFront(R53RecordSetZoneExternal):
    def setup(self):
        super(R53RecordSetCloudFront, self).setup()
        self.Condition = 'RecordSetCloudFront'
        self.AliasTarget = r53.AliasTarget(
            DNSName=GetAtt('CloudFrontDistribution', 'DomainName'),
            HostedZoneId=cfg.HostedZoneIdCF
        )
        self.Name = Sub('${EnvRole}${RecordSetCloudFrontSuffix}.cdn.' + cfg.HostedZoneNameEnv)  # Ex. client-portal.cdn.dev..
        self.Type = 'A'


class R53RecordSetLoadBalancer(R53RecordSet):
    def setup(self):
        super(R53RecordSetLoadBalancer, self).setup()
        self.AliasTarget = r53.AliasTarget(
            HostedZoneId=get_endvalue('HostedZoneIdLB')
        )
        self.Type = 'A'


class R53RecordSetEC2LoadBalancerExternal(R53RecordSetLoadBalancer, R53RecordSetZoneExternal):
    pass


class R53RecordSetEC2LoadBalancerInternal(R53RecordSetLoadBalancer, R53RecordSetZoneInternal):
    pass


class R53RecordSetECSLoadBalancer(R53RecordSetLoadBalancer):
    def setup(self, scheme):
        super(R53RecordSetECSLoadBalancer, self).setup()
        self.AliasTarget.DNSName = get_subvalue(
            'dualstack.${1E}',
            'LoadBalancerApplication%sDNS' % scheme,
            'LoadBalancerApplicationStack'
        ) 


class R53RecordSetECSLoadBalancerApplicationExternal(R53RecordSetECSLoadBalancer, R53RecordSetZoneExternal):
    pass


class R53RecordSetECSLoadBalancerApplicationInternal(R53RecordSetECSLoadBalancer, R53RecordSetZoneInternal):
    pass


class R53RecordSetEFS(R53RecordSet):
    def setup(self, efsname):
        super(R53RecordSetEFS, self).setup()
        condname = 'EFSFileSystem' + efsname  # Ex. EFSFileSystemWordPress
        self.Condition = condname
        self.HostedZoneId = Ref('HostedZonePrivate')
        self.Name = Sub('efs-%s.%s' % (efsname, cfg.HostedZoneNamePrivate))
        self.ResourceRecords = [
            Sub('${%s}.efs.${AWS::Region}.amazonaws.com' % condname)
        ]
        self.Type = 'CNAME'
        self.TTL = '300'


class R53RecordSetRDS(R53RecordSet):
    def setup(self):
        super(R53RecordSetRDS, self).setup()
        self.Type = 'CNAME'
        self.ResourceRecords = [GetAtt('DBInstance', 'Endpoint.Address')]
        self.TTL = '300'


class R53RecordSetRDSExternal(R53RecordSetRDS, R53RecordSetZoneExternal):
    pass


class R53RecordSetRDSInternal(R53RecordSetRDS, R53RecordSetZoneInternal):
    pass


class R53RecordSetCCH(R53RecordSet):
    def setup(self):
        super(R53RecordSetCCH, self).setup()
        self.Condition = 'CacheEnabled'
        self.Type = 'CNAME'
        if cfg.Engine == 'memcached':
            self.ResourceRecords = [GetAtt('CacheCluster', 'ConfigurationEndpoint.Address')]
        if cfg.Engine == 'redis':
            self.ResourceRecords = [GetAtt('CacheCluster', 'RedisEndpoint.Address')]
        self.TTL = '300'


class R53RecordSetCCHExternal(R53RecordSetCCH, R53RecordSetZoneExternal):
    pass


class R53RecordSetCCHInternal(R53RecordSetCCH, R53RecordSetZoneInternal):
    pass


class R53RecordSetNSServiceDiscovery(R53RecordSet):
    def setup(self):
        self.HostedZoneId = Ref('HostedZoneEnv')
        self.Name = Sub('find.' + cfg.HostedZoneNameEnv)
        self.ResourceRecords = GetAtt('PublicDnsNamespace', 'NameServers')
        self.Type = 'NS'
        self.TTL = '300'


class R53HostedZonePrivate(r53.HostedZone):
    def setup(self):
        self.HostedZoneConfig = r53.HostedZoneConfiguration(
            Comment=Sub('${EnvShort} private zone ${AWS::Region}')
        )
        self.Name = Sub(cfg.HostedZoneNamePrivate)
        self.VPCs = [
            r53.HostedZoneVPCs(
                VPCId=get_expvalue('VpcId'),
                VPCRegion=Ref('AWS::Region')
            )
        ]


class R53HostedZoneEnv(r53.HostedZone):
    def setup(self):
        self.Condition = self.title  # Ex. HostedZoneEnv
        self.HostedZoneConfig = r53.HostedZoneConfiguration(
            Comment=Sub('${EnvShort} public zone')
        )
        self.Name = Sub(cfg.HostedZoneNameEnv)


class R53HostedZoneEnvExtra1(r53.HostedZone):
    def setup(self):
        self.Condition = self.title  # Ex. HostedZoneEnvExtra1
        self.HostedZoneConfig = r53.HostedZoneConfiguration(
            Comment=get_subvalue('${EnvShort} ${1M} public zone', 'R53HostedZoneEnvExtra1')
        )
        self.Name = get_subvalue('${EnvShort}.${1M}', 'R53HostedZoneEnvExtra1')

# E - ROUTE53 #

# #################################
# ### START STACK INFRA CLASSES ###
# #################################

# S - ROUTE53 #
class R53_RecordSetCloudFront(object):
    def __init__(self):
        # Conditions
        C_RecordSet = {'RecordSetCloudFront': And(
            Condition('CloudFrontDistribution'),
            Not(
                Equals(get_endvalue('RecordSetCloudFront'), 'None')
            )
        )}

        add_obj([
            C_RecordSet,
        ])

        # Resources
        R_RecordSet = R53RecordSetCloudFront('RecordSetCloudFront')
        R_RecordSet.setup()

        add_obj([
            R_RecordSet,
        ])

        # Outputs
        O_CloudFront = Output('RecordSetCloudFront')
        O_CloudFront.Condition = 'RecordSetCloudFront'
        O_CloudFront.Value = Sub('${RecordSet} --> ${CloudFrontDistribution.DomainName}', **{'RecordSet': R_RecordSet.Name})

        add_obj([
            O_CloudFront
        ])


class R53_RecordSetEC2LoadBalancer(object):
    def __init__(self):
        # Resources

        # RecordSet External
        if cfg.RecordSetExternal:
            R_External = R53RecordSetEC2LoadBalancerExternal('RecordSetExternal')
            R_External.setup()

            # LoadBalancerClassic
            if cfg.LoadBalancerClassicExternal:
                R_External.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerClassicExternal.DNSName}')
            elif cfg.LoadBalancerClassicInternal:
                R_External.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerClassicInternal.DNSName}')

            # LoadBalancerApplication
            if cfg.LoadBalancerApplicationExternal:
                R_External.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerApplicationExternal.DNSName}')
            elif cfg.LoadBalancerApplicationInternal:
                R_External.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerApplicationInternal.DNSName}')

            add_obj(R_External)

            # outputs
            O_External = Output('RecordSetExternal')
            O_External.Value = Ref('RecordSetExternal')

            add_obj(O_External)

        # RecordSet Internal
        if cfg.RecordSetInternal:
            R_Internal = R53RecordSetEC2LoadBalancerInternal('RecordSetInternal')
            R_Internal.setup()

            # LoadBalancerClassic
            if cfg.LoadBalancerClassicInternal:
                R_Internal.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerClassicInternal.DNSName}')
            elif cfg.LoadBalancerClassicExternal:
                R_Internal.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerClassicExternal.DNSName}')

            # LoadBalancerApplication
            if cfg.LoadBalancerApplicationInternal:
                R_Internal.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerApplicationInternal.DNSName}')
            elif cfg.LoadBalancerApplicationExternal:
                R_Internal.AliasTarget.DNSName = Sub('dualstack.${LoadBalancerApplicationExternal.DNSName}')

            add_obj(R_Internal)

            # outputs
            O_Internal = Output('RecordSetInternal')
            O_Internal.Value = Ref('RecordSetInternal')

            add_obj(O_Internal)
# E - ROUTE53 #


class R53_RecordSetECSLoadBalancer(object):
    def __init__(self):
        # Resources
        if cfg.RecordSetExternal:
            R_External = R53RecordSetECSLoadBalancerApplicationExternal('RecordSetExternal')

            if cfg.LoadBalancerApplicationExternal:
                R_External.setup(scheme='External')
            else:
                R_External.setup(scheme='Internal')

            add_obj(R_External)
            
            # outputs
            O_External = Output('RecordSetExternal')
            O_External.Value = Ref('RecordSetExternal')

            add_obj(O_External)

        if cfg.RecordSetInternal:
            R_Internal = R53RecordSetECSLoadBalancerApplicationInternal('RecordSetInternal')

            if cfg.LoadBalancerApplicationInternal:
                R_Internal.setup(scheme='Internal')
            else:
                R_Internal.setup(scheme='External')

            add_obj(R_Internal)

            # outputs
            O_Internal = Output('RecordSetInternal')
            O_Internal.Value = Ref('RecordSetInternal')

            add_obj(O_Internal)


class R53_RecordSetRDS(object):
    def __init__(self):
        # Resources
        if cfg.RecordSetExternal:
            R_External = R53RecordSetRDSExternal('RecordSetExternal')
            R_External.setup()
            add_obj(R_External)

            # outputs
            O_External = Output('RecordSetExternal')
            O_External.Value = Ref('RecordSetExternal')

            add_obj(O_External)

        if cfg.RecordSetInternal:
            R_Internal = R53RecordSetRDSInternal('RecordSetInternal')
            R_Internal.setup()
            add_obj(R_Internal)

            # outputs
            O_Internal = Output('RecordSetInternal')
            O_Internal.Value = Ref('RecordSetInternal')

            add_obj(O_Internal)


class R53_RecordSetCCH(object):
    def __init__(self):
        # Resources
        if cfg.RecordSetExternal:
            R_External = R53RecordSetCCHExternal('RecordSetExternal')
            R_External.setup()
            add_obj(R_External)

            # outputs
            O_External = Output('RecordSetExternal')
            O_External.Value = Ref('RecordSetExternal')
            O_External.Condition = 'CacheEnabled'

            add_obj(O_External)

        if cfg.RecordSetInternal:
            R_Internal = R53RecordSetCCHInternal('RecordSetInternal')
            R_Internal.setup()
            add_obj(R_Internal)

            # outputs
            O_Internal = Output('RecordSetInternal')
            O_Internal.Value = Ref('RecordSetInternal')
            O_Internal.Condition = 'CacheEnabled'

            add_obj(O_Internal)


class R53_HostedZones(object):
    def __inita__(self, key):
        # Resources
        R_Private = R53HostedZonePrivate('HostedZonePrivate')
        R_Private.setup()

        R_Env = R53HostedZoneEnv('HostedZoneEnv')
        R_Env.setup()

        try: cfg.R53HostedZoneEnvExtra1
        except:
            pass
        else:
            # Resources
            R_EnvExtra1 = R53HostedZoneEnvExtra1('HostedZoneEnvExtra1')
            R_EnvExtra1.setup()
            add_obj(R_EnvExtra1)

        add_obj([
            R_Private,
            R_Env,
        ])

    def __init__(self, key):
        for n, v in getattr(cfg, key).iteritems():
            mapname = key + n
            resname = v['ResourceName']
            # parameters
            if n.startswith('Public'):
                p_HostedZone = Parameter(mapname)
                p_HostedZone.Description = 'Create Public %s - can be created in only one Region - empty for default based on env/role' % resname

                p_HostedZoneId = Parameter(mapname + 'Id')
                p_HostedZoneId.Description = 'Id of Public %s - required in all Regions where HostedZonePublicEnv is not created - empty for default based on env/role' % resname

                add_obj([
                    p_HostedZone,
                    p_HostedZoneId,
                ])

                # conditions
                add_obj([
                    get_condition(resname, 'not_equals', 'None', mapname)
                ])

            # resources
            r_HostedZone = r53.HostedZone(v['ResourceName'])
            auto_get_props(r_HostedZone, v, recurse=True, mapname=mapname)

            add_obj(r_HostedZone)

            # outputs
            o_HostedZoneName = Output(resname.replace('HostedZone', 'HostedZoneName'))
            o_HostedZoneName.Value = Sub(cfg.HostedZoneNamePrivate)
                
            o_HostedZoneId = Output(resname.replace('HostedZone', 'HostedZoneId'))
            o_HostedZoneId.Value = If(resname, Ref(resname), get_endvalue(mapname)) if n.startswith('Public') else Ref(resname)
            o_HostedZoneId.Export = Export(resname)

            add_obj([
                o_HostedZoneName,
                o_HostedZoneId,
            ])
