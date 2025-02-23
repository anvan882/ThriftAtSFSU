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
5. Database username: `root`
6. Database password: `csc648T15!`
7. Database name (basically the name that contains all your tables): `csc648`
8. Instructions on how to use the above information.
```bash
# How to ssh into server (be cautious!!)
ssh -i "ssh-key.pem" ubuntu@ec2-54-
215-133-155.us-west-1.compute.amazonaws.com

# How to connect to DB using SSH Tunneling
ssh -L 3307:localhost:3306 -i ssh-key.pem ubuntu@ec2-54-
215-133-155.us-west-1.compute.amazonaws.com
# -> Connect with:
mysql -h 127.0.0.1 -P 3307 -u root -p
```

# Most important things to Remember
## These values need to kept update to date throughout the semester. <br>
## <strong>Failure to do so will result it points be deducted from milestone submissions.</strong><br>
## You may store the most of the above in this README.md file. DO NOT Store the SSH key or any keys in this README.md file.
