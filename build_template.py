#!/usr/bin/env python3
"""Generate deploy/template.yaml: a single CloudFormation template with the app embedded.

Usage:  python3 build_template.py
"""
import base64
import io
import os
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "app")


def bundle():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, dirs, files in os.walk(APP):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith((".db", ".pyc")):
                    continue
                full = os.path.join(root, f)
                tar.add(full, arcname=os.path.relpath(full, APP))
    return base64.b64encode(buf.getvalue()).decode()


TEMPLATE = """\
AWSTemplateFormatVersion: '2010-09-09'
Description: Student Management System - one-click deploy (EC2 + Elastic IP)

Parameters:
  AdminUsername:
    Type: String
    Default: admin
    AllowedPattern: '[A-Za-z0-9_]{{3,32}}'
    Description: Login username for the admin account
  AdminPassword:
    Type: String
    NoEcho: true
    MinLength: 8
    MaxLength: 64
    AllowedPattern: '[A-Za-z0-9]+'
    ConstraintDescription: Letters and numbers only, at least 8 characters
    Description: Login password for the admin account (letters and numbers only)
  InstanceType:
    Type: String
    Default: t3.micro
    AllowedValues: [t3.micro, t3.small, t3.medium, t2.micro]
  LatestAmiId:
    Type: AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>
    Default: /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64

Resources:
  WebSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Allow HTTP to the student management app
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0

  InstanceRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal: {{ Service: ec2.amazonaws.com }}
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

  InstanceProfile:
    Type: AWS::IAM::InstanceProfile
    Properties:
      Roles: [!Ref InstanceRole]

  AppServer:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !Ref LatestAmiId
      InstanceType: !Ref InstanceType
      IamInstanceProfile: !Ref InstanceProfile
      SecurityGroupIds: [!GetAtt WebSecurityGroup.GroupId]
      BlockDeviceMappings:
        - DeviceName: /dev/xvda
          Ebs: {{ VolumeSize: 10, VolumeType: gp3, Encrypted: true }}
      Tags:
        - Key: Name
          Value: student-management-system
      UserData:
        Fn::Base64: !Sub |
          #!/bin/bash
          set -ex
          dnf install -y python3-pip
          mkdir -p /opt/sms/app /opt/sms/data
          echo '{bundle}' | base64 -d | tar xz -C /opt/sms/app
          pip3 install -r /opt/sms/app/requirements.txt
          cat > /etc/sms.env <<EOF
          ADMIN_USER=${{AdminUsername}}
          ADMIN_PASS=${{AdminPassword}}
          SMS_DB=/opt/sms/data/students.db
          SECRET_KEY=$(openssl rand -hex 24)
          EOF
          chmod 600 /etc/sms.env
          cat > /etc/systemd/system/sms.service <<EOF
          [Unit]
          Description=Student Management System
          After=network.target
          [Service]
          WorkingDirectory=/opt/sms/app
          EnvironmentFile=/etc/sms.env
          ExecStart=/usr/local/bin/gunicorn -w 2 -b 0.0.0.0:80 app:app
          AmbientCapabilities=CAP_NET_BIND_SERVICE
          Restart=always
          [Install]
          WantedBy=multi-user.target
          EOF
          systemctl daemon-reload
          systemctl enable --now sms

  ElasticIP:
    Type: AWS::EC2::EIP
    Properties:
      InstanceId: !Ref AppServer

Outputs:
  AppURL:
    Description: Open this URL in your browser (give it ~3 minutes after the stack finishes)
    Value: !Sub http://${{ElasticIP}}
  Username:
    Value: !Ref AdminUsername
"""

if __name__ == "__main__":
    out = os.path.join(HERE, "template.yaml")
    with open(out, "w") as f:
        f.write(TEMPLATE.format(bundle=bundle()))
    print("wrote", out, os.path.getsize(out), "bytes")
