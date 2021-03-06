import troposphere.s3 as s3

from .common import *
from .shared import (Parameter, do_no_override, get_endvalue, get_expvalue,
                     get_subvalue, auto_get_props, get_condition, add_obj)
from .iam import (IAMRoleBucketReplica, IAMPolicyBucketReplica,
                  IAMPolicyStatement)
from .cloudfront import CFOriginAccessIdentity
from .lambdas import LambdaPermissionS3


class S3ReplicationConfiguration(s3.ReplicationConfiguration):
    def __init__(self, name, key, **kwargs):
        super().__init__(**kwargs)

        self.Role = GetAtt(f'Role{name}Replica', 'Arn')
        self.Rules = [
            s3.ReplicationConfigurationRules(
                Destination=s3.ReplicationConfigurationRulesDestination(
                    Bucket=get_subvalue(
                        'arn:aws:s3:::${1M}', f'{name}ReplicaDstBucket'
                    ) if 'ReplicaDstBucket' in key
                    else get_subvalue(
                        'arn:aws:s3:::${1M}-%s'
                        % bucket_name.replace('${AWS::Region}-', '', 1),
                        f'{name}ReplicaDstRegion',
                    ),
                    AccessControlTranslation=If(
                        f'{name}ReplicaDstOwner',
                        s3.AccessControlTranslation(
                            Owner='Destination'
                        ),
                        Ref('AWS::NoValue')
                    ),
                    Account=If(
                        f'{name}ReplicaDstOwner',
                        get_endvalue(f'{name}ReplicaDstOwner'),
                        Ref('AWS::NoValue')
                    ),
                ),
                Prefix=(get_endvalue(f'{name}ReplicaDstPrefix')
                        if 'ReplicaDstPrefix' in key else ''),
                Status='Enabled'
            )
        ]


class S3Bucket(s3.Bucket):
    def __init__(self, title, key, **kwargs):
        super().__init__(title, **kwargs)

        name = self.title  # Ex. BucketStatic
        auto_get_props(self, key, recurse=True)
        self.Condition = name
        self.BucketName = Sub(bucket_name)
        self.CorsConfiguration = If(
            f'{name}Cors',
            s3.CorsConfiguration(
                CorsRules=[
                    s3.CorsRules(
                        AllowedHeaders=['Authorization'],
                        AllowedMethods=['GET'],
                        AllowedOrigins=['*'],
                        MaxAge=3000
                    )
                ]
            ),
            Ref('AWS::NoValue')
        )
        self.ReplicationConfiguration = If(
            f'{name}Replica',
            S3ReplicationConfiguration(name=name, key=key),
            Ref('AWS::NoValue'),
        )
        self.VersioningConfiguration = If(
            f'{name}Versioning',
            s3.VersioningConfiguration(
                Status=get_endvalue(f'{name}Versioning')
            ),
            Ref('AWS::NoValue')
        )


class S3BucketPolicy(s3.BucketPolicy):
    def __init__(self, title, key, **kwargs):
        super().__init__(title, **kwargs)

        if 'Condition' in key:
            self.Condition = key['Condition']
        self.PolicyDocument = {
            'Version': '2012-10-17',
        }


def S3BucketPolicyStatementBase(bucket):
    statements = []
    statements.append({
        'Action': [
            's3:GetBucketLocation'
        ],
        'Effect': 'Allow',
        'Resource': Sub('arn:aws:s3:::%s' % bucket_name),
        'Principal': {
            'AWS': Sub('arn:aws:iam::${AWS::AccountId}:root')
        },
        'Sid': 'Base'
    })
    return statements


def S3BucketPolicyStatementReplica(bucket, key):
    statements = []
    if_statements = []
    condition = f'{bucket}ReplicaSrcAccount'
    statements.append({
        'Action': [
            's3:ReplicateObject',
            's3:ReplicateDelete',
            's3:ObjectOwnerOverrideToBucketOwner',
            ],
        'Effect': 'Allow',
        'Resource': [
            get_subvalue(
                'arn:aws:s3:::%s/${1M}*' % bucket_name,
                f'{bucket}ReplicaSrcPrefix'
            ) if 'ReplicaSrcPrefix' in key else Sub(
                'arn:aws:s3:::%s/*' % bucket_name),
        ],
        'Principal': {
            'AWS': [
                get_subvalue(
                    'arn:aws:iam::${1M}:root', f'{bucket}ReplicaSrcAccount')
            ]
        },
        'Sid': 'AllowReplica'
    })

    for s in statements:
        if_statements.append(
            If(
                condition,
                s,
                Ref('AWS::NoValue')
            )
        )

    return if_statements


def S3BucketPolicyStatementCFOriginAccessIdentity(bucket, principal):
    statements = []
    statements.append(
        {
            'Action': [
                's3:GetObject'
            ],
            'Effect': 'Allow',
            'Resource': [
                Sub('arn:aws:s3:::%s/*' % bucket_name)
            ],
            'Principal': {
                'AWS': principal
            },
            'Sid': 'AllowCFAccess'
        },
    )
    return statements


def S3BucketPolicyStatementSes(bucket):
    statements = []
    statements.append(
        {
            'Action': [
                's3:PutObject'
            ],
            'Effect': 'Allow',
            'Resource': [
                Sub('arn:aws:s3:::%s/*' % bucket_name)
            ],
            'Principal': {
                'Service': 'ses.amazonaws.com'
            },
            'Condition': {
                'StringEquals': {
                    'aws:Referer': Ref('AWS::AccountId')
                },
            },
            'Sid': 'AllowSES'
        },
    )
    return statements


def S3BucketPolicyStatementRead(bucket, principal):
    statements = []
    if_statements = []
    condition = f'{bucket}PolicyRead'
    statements.append({
        'Action': [
            's3:ListBucket',
            's3:GetBucketLocation',
            's3:ListBucketMultipartUploads',
            's3:ListBucketVersions'
        ],
        'Effect': 'Allow',
        'Resource': [
            Sub('arn:aws:s3:::%s' % bucket_name)
        ],
        'Principal': {
            'AWS': principal
        },
        'Sid': 'AllowListBucket'
    })
    statements.append({
        'Action': [
            's3:GetObject',
            's3:ListMultipartUploadParts'
        ],
        'Effect': 'Allow',
        'Resource': [
            Sub('arn:aws:s3:::%s/*' % bucket_name)
        ],
        'Principal': {
            'AWS': principal
        },
        'Sid': 'AllowGetObject'
    })

    for s in statements:
        if_statements.append(
            If(
                condition,
                s,
                Ref('AWS::NoValue')
            )
        )

    return if_statements


def S3BucketPolicyStatementWrite(bucket, principal):
    statements = []
    if_statements = []
    condition = f'{bucket}PolicyWrite'
    statements.append({
        'Action': [
            's3:Put*',
        ],
        'Effect': 'Allow',
        'Resource': [
            Sub('arn:aws:s3:::%s/*' % bucket_name)
        ],
        'Principal': {
            'AWS': principal
        },
        'Sid': 'AllowPut'
    })

    for s in statements:
        if_statements.append(
            If(
                condition,
                s,
                Ref('AWS::NoValue')
            )
        )

    return if_statements


# #################################
# ### START STACK INFRA CLASSES ###
# #################################

class S3_Buckets(object):

    def __init__(self, key):
        global bucket_name

        for n, v in getattr(cfg, key).items():
            resname = f'{key}{n}'
            name = n
            if not ('Enabled' in v and v['Enabled'] is True):
                continue
            bucket_name = getattr(cfg, resname)
            # parameters
            p_ReplicaDstRegion = Parameter(f'{resname}ReplicaDstRegion')
            p_ReplicaDstRegion.Description = (
                'Region to Replicate Bucket - None to disable - '
                'empty for default based on env/role')
            p_ReplicaDstRegion.AllowedValues = ['', 'None'] + cfg.regions

            add_obj(p_ReplicaDstRegion)

            PolicyReadConditions = []
            PolicyReadPrincipal = []

            for m, w in v['AccountsRead'].items():
                accountread_name = f'{resname}AccountsRead{m}'
                # conditions
                add_obj(get_condition(accountread_name, 'not_equals', 'None'))

                PolicyReadConditions.append(Condition(accountread_name))
                PolicyReadPrincipal.append(If(
                    accountread_name,
                    get_subvalue('arn:aws:iam::${1M}:root', accountread_name),
                    Ref('AWS::NoValue')
                ))

            # conditions
            if PolicyReadConditions:
                c_PolicyRead = {f'{resname}PolicyRead': Or(
                    Equals('1', '0'),
                    Equals('1', '0'),
                    *PolicyReadConditions
                )}
            else:
                c_PolicyRead = {f'{resname}PolicyRead': Equals('True', 'False')}

            PolicyWriteConditions = []
            PolicyWritePrincipal = []

            for m, w in v['AccountsWrite'].items():
                accountwrite_name = f'{resname}AccountsWrite{m}'
                # conditions
                add_obj(get_condition(accountwrite_name, 'not_equals', 'None'))

                PolicyWriteConditions.append(Condition(accountwrite_name))
                PolicyWritePrincipal.append(If(
                    accountwrite_name,
                    get_subvalue('arn:aws:iam::${1M}:root', accountwrite_name),
                    Ref('AWS::NoValue')
                ))

            # conditions
            if PolicyWriteConditions:
                c_PolicyWrite = {f'{resname}PolicyWrite': Or(
                    Equals('1', '0'),
                    Equals('1', '0'),
                    *PolicyWriteConditions
                )}
            else:
                c_PolicyWrite = {f'{resname}PolicyWrite': Equals('True', 'False')}


            c_Create = get_condition(
                resname, 'not_equals', 'None', f'{resname}Create')

            c_Versioning = get_condition(
                f'{resname}Versioning', 'not_equals', 'None')

            c_Cors = get_condition(
                f'{resname}Cors', 'not_equals', 'None')

            c_ReplicaSrcAccount = get_condition(
                f'{resname}ReplicaSrcAccount', 'not_equals', 'None')

            c_ReplicaDstOwner = get_condition(
                f'{resname}ReplicaDstOwner', 'not_equals', 'None')

            # c_AccountRO = get_condition(
            #    f'{resname}AccountRO', 'not_equals', 'None')

            c_Replica = {f'{resname}Replica': And(
                Condition(resname),
                get_condition(
                    '', 'not_equals', 'None', f'{resname}ReplicaDstRegion')
            )}

            add_obj([
                c_PolicyRead,
                c_PolicyWrite,
                c_Create,
                c_Versioning,
                c_Cors,
                c_ReplicaSrcAccount,
                c_ReplicaDstOwner,
                c_Replica,
            ])

            # resources
            BucketPolicyStatement = []

            r_Bucket = S3Bucket(resname, key=v)

            r_Policy = S3BucketPolicy(f'BucketPolicy{name}', key=v)
            r_Policy.Condition = resname
            r_Policy.Bucket = Sub(bucket_name)
            r_Policy.PolicyDocument['Statement'] = BucketPolicyStatement

            # At least one statement must be always present,
            # create a simple one with no conditions
            BucketPolicyStatement.extend(
                S3BucketPolicyStatementBase(resname))

            BucketPolicyStatement.extend(
                S3BucketPolicyStatementReplica(resname, v))

            r_Role = IAMRoleBucketReplica(f'Role{resname}Replica')

            BucketPolicyStatement.extend(
                S3BucketPolicyStatementRead(resname, PolicyReadPrincipal))

            BucketPolicyStatement.extend(
                S3BucketPolicyStatementWrite(resname, PolicyWritePrincipal))

            r_IAMPolicyReplica = IAMPolicyBucketReplica(
                f'IAMPolicyReplicaBucket{name}',
                bucket=resname, bucket_name=bucket_name, key=v)

            try:
                lambda_arn = eval(
                    v['NotificationConfiguration']['LambdaConfigurations']
                    ['Trigger']['Function']
                )
            except:
                pass
            else:
                if 'Fn::GettAtt' in lambda_arn.data:
                    permname = '%s%s' % (
                        lambda_arn.data['Fn::GettAtt'].replace(
                            'Lambda', 'LambdaPermission'),
                        resname)
                else:
                    permname = 'LambdaPermission'

                r_LambdaPermission = LambdaPermissionS3(
                    permname, key=lambda_arn, source=resname)

                add_obj(r_LambdaPermission)

                BucketPolicyStatement.extend(
                    S3BucketPolicyStatementSes(resname))

            if 'WebsiteConfiguration' in v:
                r_Bucket.WebsiteConfiguration = s3.WebsiteConfiguration(
                    f'{resname}WebsiteConfiguration')
                auto_get_props(
                    r_Bucket.WebsiteConfiguration, v['WebsiteConfiguration'],
                    recurse=True)

            if 'PolicyStatement' in v:
                FixedStatements = []
                for fsn, fsv in v['PolicyStatement'].items():
                    FixedStatement = IAMPolicyStatement(fsv)
                    FixedStatement['Principal'] = {
                        'AWS': eval(fsv['Principal'])
                    }
                    FixedStatement['Sid'] = fsv['Sid']
                    FixedStatements.append(FixedStatement)
                BucketPolicyStatement.extend(FixedStatements)

            PolicyCloudFrontOriginAccessIdentityPrincipal = []
            if 'CloudFrontOriginAccessIdentity' in v:
                identityname = v['CloudFrontOriginAccessIdentity']
                identityresname = (
                    f'CloudFrontOriginAccessIdentity{identityname}')

                PolicyCloudFrontOriginAccessIdentityPrincipal.append(
                    Sub('arn:aws:iam::cloudfront:user/'
                        'CloudFront Origin Access Identity ${%s}'
                        % identityresname)
                )

                for ixn, ixv in (
                        v['CloudFrontOriginAccessIdentityExtra'].items()):
                    ixname = (
                        f'{resname}CloudFrontOriginAccessIdentityExtra{ixn}')
                    # conditions
                    add_obj(get_condition(ixname, 'not_equals', 'None'))

                    PolicyCloudFrontOriginAccessIdentityPrincipal.append(If(
                        ixname,
                        get_subvalue(
                            'arn:aws:iam::cloudfront:user/'
                            'CloudFront Origin Access Identity ${1M}', ixname),
                        Ref('AWS::NoValue')
                    ))

                # conditions
                identitycondname = f'{resname}CloudFrontOriginAccessIdentity' 
                c_identity = get_condition(
                    identitycondname, 'not_equals', 'None')

                add_obj(c_identity)

                # resources
                BucketPolicyStatement.extend(
                    S3BucketPolicyStatementCFOriginAccessIdentity(
                        resname,
                        PolicyCloudFrontOriginAccessIdentityPrincipal)
                )

                r_OriginAccessIdentity = CFOriginAccessIdentity(
                    identityresname, comment=identityname)
                r_OriginAccessIdentity.Condition = identitycondname

                add_obj([
                    r_OriginAccessIdentity,
                ])

                # outputs
                o_OriginAccessIdentity = Output(identityresname)
                o_OriginAccessIdentity.Value = Ref(identityresname)
                o_OriginAccessIdentity.Condition = identitycondname

                add_obj(o_OriginAccessIdentity)

            add_obj([
                r_Bucket,
                r_Policy,
                # r_PolicyReplica,
                # r_PolicyRO,
                r_IAMPolicyReplica,
                r_Role
            ])

            # outputs
            outvaluebase = Sub(bucket_name)
            if 'OutputValueRegion' in v:
                condname = f'{resname}OutputValueRegion'
                # conditions
                add_obj(get_condition(condname, 'not_equals', 'AWSRegion'))

                outvaluebase = If(
                    condname,
                    Sub('${Region}-%s'
                        % bucket_name.replace('${AWS::Region}-', '', 1),
                        **{'Region': get_endvalue(condname)}),
                    outvaluebase
                )

            o_Bucket = Output(resname)
            o_Bucket.Value = If(
                resname,
                Ref(resname),
                outvaluebase
            )
            if resname == 'BucketAppRepository':
                o_Bucket.Export = Export(resname)

            add_obj([
                o_Bucket,
            ])


# no more used
class S3_BucketPolicies(object):
    def __init__(self, key):
        for n, v in getattr(cfg, key).items():
            resname = f'{key}{n}'
            Statements = []
            for m, w in v['Statement'].items():
                Statement = IAMPolicyStatement(w)
                Statement['Principal'] = {
                    'AWS': eval(w['Principal'])
                }
                Statements.append(Statement)

            r_Policy = S3BucketPolicy(resname, key=v)
            r_Policy.Bucket = get_endvalue(f'{resname}Bucket')
            r_Policy.PolicyDocument['Statement'] = Statement

            add_obj(r_Policy)
