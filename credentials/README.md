# Credentials Folder

## The purpose of this folder is to store all credentials needed to log into your server and databases. This is important for many reasons. But the two most important reasons is
    1. Grading , servers and databases will be logged into to check code and functionality of application. Not changes will be unless directed and coordinated with the team.
    2. Help. If a class TA or class CTO needs to help a team with an issue, this folder will help facilitate this giving the TA or CTO all needed info AND instructions for logging into your team's server. 


# Below is a list of items required. Missing items will causes points to be deducted from multiple milestone submissions.

1. Server URL or IP: `54.215.133.155`
2. SSH username: `ubuntu`
3. SSH password or key.
    <br> If a ssh key is used please upload the key to the credentials folder.
    <br> `ssh-key.pem`
4. Database URL or IP and port used.
    <br><strong> NOTE THIS DOES NOT MEAN YOUR DATABASE NEEDS A PUBLIC FACING PORT.</strong> But knowing the IP and port number will help with SSH tunneling into the database. The default port is more than sufficient for this class.
    <br>`127.0.0.1:3306`
5. Database username: `ubuntu`
6. Database password: `921652677`
7. Database name (basically the name that contains all your tables): `ubuntu`
8. Instructions on how to use the above information.
```bash
# How to ssh into server (be cautious!!)
ssh -i "ssh-key.pem" ubuntu@54.215.133.155

# Connect to SQL through SSH on SQLWB
Connection Name: SqlEc2
SSH Hostname: 54.215.133.155
SSH username: ubuntu
SSH Key File: path you your key file
MySQL Hostname: 127.0.0.1
MySQL Server Port: 3306
Username: ubuntu
Password: 921652677

# Create SSH Tunnel from Local VM to EC2 Example
ssh -fN -L 3306:localhost:3306 ubuntu@54.215.133.155 -i /home/sid/Code/csc648-fa25-0104-team15/credentials/ssh-key.pem

# To Kill Tunnel
ps -ef | grep "ssh -fN -L 3306:localhost:3306" | grep -v grep | awk '{print $2}' | xargs kill
```

# Most important things to Remember
## These values need to kept update to date throughout the semester. <br>
## <strong>Failure to do so will result it points be deducted from milestone submissions.</strong><br>
## You may store the most of the above in this README.md file. DO NOT Store the SSH key or any keys in this README.md file.
