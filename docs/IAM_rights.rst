==========
IAM rights
==========

These are the IAM rights for the images running under AWS when built with the 20ft CloudFormation stack...

Nodes
=====
::

    logs:CreateLog*
    logs:PutLog*
    logs:Describe*
    ssm:DeleteParameter
    ssm:DescribeParameters
    ssm:GetParameter*
    ssm:PutParameter
    cloudwatch:GetMetric*
    cloudwatch:ListMetrics
    cloudwatch:PutMetricData

Broker
======

No user code is run on the broker. ::

    ec2:AllocateAddress
    ec2:AllocateHosts
    ec2:AssignPrivateIpAddresses
    ec2:AssociateAddress
    ec2:AssociateIamInstanceProfile
    ec2:AttachInternetGateway
    ec2:AttachNetworkInterface
    ec2:AttachVolume
    ec2:CreateNetworkInterface
    ec2:DeleteNetworkInterface
    ec2:Describe*
    ec2:DetachNetworkInterface
    ec2:DisassociateAddress
    ec2:ModifyInstanceAttribute
    ec2:ModifyNetworkInterfaceAttribute
    ec2:RebootInstances
    ec2:ReleaseAddress
    ec2:ReleaseHosts
    ec2:ReportInstanceStatus
    ec2:RunInstances
    ec2:StartInstances
    ec2:StopInstances
    ec2:TerminateInstances
    ec2:UpdateSecurityGroupRuleDescriptionsEgress
    ec2:UpdateSecurityGroupRuleDescriptionsIngress
    ec2:UnassignPrivateIpAddresses
    ec2:ReplaceIamInstanceProfile
    elasticfilesystem:*
    logs:CreateLog*
    logs:PutLog*
    logs:Describe*
    ssm:DeleteParameter
    ssm:DescribeParameters
    ssm:GetParameter*
    ssm:PutParameter
    cloudwatch:GetMetric*
    cloudwatch:ListMetrics
    cloudwatch:PutMetricData
    ec2messages:*
    ssm:UpdateInstanceInformation
    ssm:ListInstanceAssociations
    ssm:Describe*
    iam:PassRole
