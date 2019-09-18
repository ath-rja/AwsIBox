from collections import OrderedDict, Mapping
import troposphere.apigateway as agw

from .common import *
from .shared import (Parameter, do_no_override, get_endvalue, get_expvalue,
    get_subvalue, auto_get_props, get_condition)
from .lambdas import LambdaPermissionApiGateway


class ApiGatewayAccount(agw.Account):
    def setup(self):
        self.CloudWatchRoleArn = get_expvalue('RoleApiGatewayCloudWatch')


class ApiGatewayResource(agw.Resource):
    def setup(self, key, stage):
        mapname = 'ApiGatewayStage' + stage + 'ApiGatewayResource'
        stagekey = cfg.ApiGatewayStage[stage]['ApiGatewayResource']
        auto_get_props(self, key)
        self.RestApiId = Ref('ApiGatewayRestApi')
        auto_get_props(self, stagekey, mapname=mapname, recurse=True, rootkey=key, rootname=self.title)


class ApiGatewayMethod(agw.Method):
    def setup(self, key, basename, name, stage):
        mapname = 'ApiGatewayStage' + stage + 'ApiGatewayResource' + basename + 'Method' + name
        stagekey = cfg.ApiGatewayStage[stage]['ApiGatewayResource'][basename]['Method'][name] 
        auto_get_props(self, key, recurse=True)
        self.RestApiId = Ref('ApiGatewayRestApi')
        self.ResourceId = Ref('ApiGatewayResource' + basename)
        auto_get_props(self, stagekey, mapname=mapname, recurse=True, rootkey=key, rootname=self.title)
        # If Uri is a lambda get same stage version lambda name Ex. LambdaPaidApiv1
        if ':lambda:' in self.Integration.Uri:
            st = self.Integration.Uri
            l = st.rfind('.')
            self.Integration.Uri = Sub(st[0:l] + stage + st[l:])


class ApiGatewayStage(agw.Stage):
    def setup(self, name, key):
        self.StageName = name
        auto_get_props(self, key, recurse=True)
        self.RestApiId = Ref('ApiGatewayRestApi')
        self.DeploymentId = Ref('ApiGatewayDeployment' + name)


class ApiGatewayDeployment(agw.Deployment):
    def setup(self, name, key):
        lastresource = next(reversed(cfg.ApiGatewayResource))
        lastmethod = next(reversed(cfg.ApiGatewayResource[lastresource]['Method']))
        self.DependsOn = 'ApiGatewayResource' + lastresource + 'Method' + lastmethod
        self.Description = Ref('Deployment' + name + 'Description')
        self.RestApiId = Ref('ApiGatewayRestApi')


class AGW_Account(object):
    def __init__(self, key):
        # Resources
        R_Account = ApiGatewayAccount('ApiGatewayAccount')
        R_Account.setup()

        cfg.Resources.extend([
            R_Account,
        ])


class AGW_UsagePlans(object):
    def __init__(self, key):
        for n, v in getattr(cfg, key).iteritems():
            resname = key + n
            for m, w in v['ApiStages'].iteritems():
                # parameters
                p_Stage = Parameter(resname + 'ApiStages' + m + 'Stage')
                p_Stage.Description = m + ' Stage - empty for default based on env/role'

                cfg.Parameters.append(p_Stage)

            # resources
            r_UsagePlan = agw.UsagePlan(resname)
            auto_get_props(r_UsagePlan, v, recurse=True)

            cfg.Resources.extend([
                r_UsagePlan,
            ])

            # outputs
            o_UsagePlan = Output(resname)
            o_UsagePlan.Value = Ref(resname)
            o_UsagePlan.Export = Export(resname)

            cfg.Outputs.extend([
                o_UsagePlan,
            ])


class AGW_ApiKeys(object):
    def __init__(self, key):
        for n, v in getattr(cfg, key).iteritems():
            resname = key + n
            # parameters
            p_Enabled = Parameter(resname + 'Enabled')
            p_Enabled.Description = resname + 'Enabled - empty for default based on env/role'

            p_UsagePlan = Parameter(resname + 'UsagePlan')
            p_UsagePlan.Description = resname + 'UsagePlan - empty for default based on env/role'

            cfg.Parameters.extend([
                p_Enabled,
                p_UsagePlan,
            ])
            
            # resources
            r_ApiKey = agw.ApiKey(resname)
            auto_get_props(r_ApiKey, v, recurse=True)

            cfg.Resources.extend([
                r_ApiKey,
            ])

            if 'UsagePlan' in v:
                plankey_name = resname + 'UsagePlan'
                r_UsagePlanKey = agw.UsagePlanKey('ApiGatewayUsagePlan' + n)
                r_UsagePlanKey.KeyId = Ref(resname)
                r_UsagePlanKey.KeyType = 'API_KEY'
                r_UsagePlanKey.UsagePlanId = ImportValue(get_subvalue('ApiGatewayUsagePlan${1M}', resname + 'UsagePlan'))

                cfg.Resources.append(r_UsagePlanKey)
            
            # Outputs
            o_ApiKey = Output(resname)
            o_ApiKey.Value = Ref(resname)


class AGW_Stages(object):
    def __init__(self, key):
        for n, v in getattr(cfg, key).iteritems():
            # parameters
            p_DeploymentDescription = Parameter('Deployment' + n + 'Description')
            p_DeploymentDescription.Description = 'Deployment' + n + ' Description'
            p_DeploymentDescription.Default = n

            cfg.Parameters.extend([
                p_DeploymentDescription,
            ])

            # resources
            resname = key + n
            r_Stage = ApiGatewayStage(resname)
            r_Stage.setup(name=n, key=v)

            r_Deployment = ApiGatewayDeployment('ApiGatewayDeployment' + n)
            r_Deployment.setup(name=n, key=v)

            cfg.Resources.extend([
                r_Stage,
                r_Deployment,
            ])
       

class AGW_RestApi(object):
    def __init__(self, key):
        # Resources
        R_RestApi = agw.RestApi('ApiGatewayRestApi')
        auto_get_props(R_RestApi, mapname='')
        R_RestApi.EndpointConfiguration = agw.EndpointConfiguration(
            Types=get_endvalue('EndpointConfiguration')
        )

        cfg.Resources.extend([
            R_RestApi,
        ])

        for n, v in getattr(cfg, key).iteritems():
            resname = key + n
            agw_stage = cfg.Stage
            r_Resource = ApiGatewayResource(resname)
            r_Resource.setup(key=v, stage=agw_stage)

            for m, w in v['Method'].iteritems():
                r_Method = ApiGatewayMethod(resname + 'Method' + m)
                r_Method.setup(key=w, basename=n, name=m, stage=agw_stage)

                cfg.Resources.extend([
                    r_Resource,
                    r_Method,
                ])

        for l, w in cfg.Lambda.iteritems():
            r_LambdaPermission = LambdaPermissionApiGateway('LambdaPermission' + l)
            r_LambdaPermission.setup(
                name=Ref('Lambda' + l),
                source=Sub('arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${ApiGatewayRestApi}/*/*/*')
            )

            cfg.Resources.append(r_LambdaPermission)

        # Outputs
        O_InvokeUrl = Output('InvokeUrl')
        O_InvokeUrl.Value = Sub('https://${ApiGatewayRestApi}.execute-api.${AWS::Region}.amazonaws.com/' + cfg.Stage)

        cfg.Outputs.extend([
            O_InvokeUrl,
        ])
