# Student Management System (cloud-ready)

A small web app for managing students, courses, enrollments and grades, with an admin login.
Built with Flask + SQLite, and deployable to AWS in one click using CloudFormation.

## Features
- Admin login (username/password set at deploy time), CSRF protection
- Students: add, edit, delete, search (name, roll no, department, email)
- Courses: add, delete, see how many students are enrolled
- Enrollments: enroll a student in a course, record a grade, remove
- Dashboard with totals and students-per-department

## Deploy to AWS (about 5 minutes)

1. Sign in to the AWS Console and pick a region (e.g. Asia Pacific (Mumbai) `ap-south-1`).
2. Open **CloudFormation → Create stack → With new resources**.
3. Choose **Upload a template file** and select `deploy/template.yaml`.
4. Enter a stack name (e.g. `student-management`), an **AdminPassword** (letters and numbers only, 8+ chars), and click through to **Submit**.
5. Wait until the stack status is `CREATE_COMPLETE` (~3 minutes), then open the **Outputs** tab and click `AppURL`.
6. Allow another 2-3 minutes after completion for the server to install dependencies if the page isn't up yet. Log in with your username and password.

What it creates: one EC2 instance (t3.micro, Amazon Linux 2023), a security group (port 80 only), an Elastic IP so the URL doesn't change, and an IAM role for AWS Systems Manager access (no SSH keys needed).

**To remove everything** (and stop charges): delete the stack in CloudFormation. Note this also deletes the data.

Using the AWS CLI instead:

```bash
aws cloudformation deploy \
  --stack-name student-management \
  --template-file deploy/template.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides AdminPassword=ChangeMe12345
aws cloudformation describe-stacks --stack-name student-management \
  --query "Stacks[0].Outputs"
```

## Run locally

```bash
cd app
pip install -r requirements.txt
python app.py          # http://localhost:5000  (login: admin / admin123)
```

Override credentials with env vars `ADMIN_USER`, `ADMIN_PASS`, `SECRET_KEY`; database location with `SMS_DB`.

## Changing the app, then redeploying

Edit files in `app/`, then run `python3 deploy/build_template.py` to regenerate `deploy/template.yaml`
(the app is embedded in the template). Create a new stack with it.

## Project structure

```
app/                Flask application (app.py, templates/, requirements.txt)
deploy/
  build_template.py Generates template.yaml with the app embedded
  template.yaml     One-click CloudFormation template
```

## Notes for your report / viva
- Architecture: browser → Elastic IP → EC2 (gunicorn + Flask) → SQLite on an encrypted EBS volume.
- Possible upgrades to mention: Amazon RDS instead of SQLite, an Application Load Balancer with HTTPS (ACM certificate), Auto Scaling, CloudWatch monitoring, role-based users (admin/teacher/student).
- Traffic is plain HTTP; add HTTPS before storing real student data.
