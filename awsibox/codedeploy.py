import troposphere.codedeploy as cdd

from .common import *
from .shared import (Parameter, do_no_override, get_endvalue, get_expvalue,
    get_subvalue, auto_get_props, get_condition)


class CDEc2TagFilters(cdd.Ec2TagFilters):
    def __init__(self, title, **kwargs):
        super(CDEc2TagFilters, self).__init__(title, **kwargs)
        self.Key = 'EnvStackName'
        self.Type = 'KEY_AND_VALUE'
        self.Value = Ref('AWS::StackName')


class CDDeploymentGroup(cdd.DeploymentGroup):
    def setup(self, index):
        appreponame = 'Apps%sRepoName' % index
        appenvname = 'EnvApp%sVersion' % index
        self.Condition = 'DeploymentGroup'
        self.ApplicationName = get_endvalue(appreponame)
        # Uncomment for old behaviour where codedeploy prepare at boot autoscalinggroup's instances (do not work with autospot)
        #self.AutoScalingGroups = If(
        #    'DeployRevision',
        #    [Ref('AutoScalingGroup')],
        #    Ref('AWS::NoValue')
        #)
        # AUTOSPOT - Use Ec2TagFilters to let it work with instances launched by autospot
        self.Ec2TagFilters = If(
            'DeployRevision',
            [CDEc2TagFilters('')],
            Ref('AWS::NoValue')
        )
        self.Deployment = If(
            'DeployRevision',
            cdd.Deployment(
                Revision=cdd.Revision(
                    RevisionType='S3',
                    S3Location=cdd.S3Location(
                        Bucket=Sub(cfg.BucketAppRepository),
                        BundleType='tgz',
                        Key=get_subvalue('${1M}/${1M}-${%s}.tar.gz' % appenvname, appreponame)
                    )   
                )   
            ),  
            Ref('AWS::NoValue')
        )   
        self.DeploymentGroupName = Sub('${AWS::StackName}.${EnvRole}')
        self.ServiceRoleArn = get_expvalue('RoleCodeDeploy', '')

# #################################
# ### START STACK INFRA CLASSES ###
# #################################

class CD_DeploymentGroup(object):
    def __init__(self):
        # Conditions
        do_no_override(True)
        C_DeploymentGroup = {'DeploymentGroup': And(
            Condition('Apps1'),
            Equals(get_endvalue('DeploymentGroup'), True),
        )}

        C_DeployRevision = {'DeployRevision': Equals(
            Ref('UpdateMode'), 'CodeDeploy'
        )}

        cfg.Conditions.extend([
            C_DeploymentGroup,
            C_DeployRevision,
        ])
        do_no_override(False)

        # Resources
        # FOR SINGLEAPP CODEDEPLOY
        if len(cfg.Apps) == 1:
            R_DeploymentGroup = CDDeploymentGroup('DeploymentGroup')
            R_DeploymentGroup.setup(index=1)

            cfg.Resources.append(R_DeploymentGroup)


class CD_Applications(object):
    def __init__(self, key):
        for n, v in getattr(cfg, key).iteritems():
            App = cdd.Application(key + n)
            App.ApplicationName = get_endvalue(key + n)

            cfg.Resources.append(App)
