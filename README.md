# HP Insight Remote Support REST API


You can use this API as part of your automation process to:
- add/remove HP Servers to/from HP IRS. (/v1/irs/node/*) endpoint
- check the current state of your case ID and perform an action based on your automation workflow. (/v1/irs/instance/*) endpoint

# API endpoints:

* /v1/irs/node/add/<hostname> - register iLO hostname in IRS
* /v1/irs/node/del/<hostname> - unregister iLO hostname from IRS
* /v1/irs/node/status/<hostname> - whether or not a host is registered in IRS
* /v1/irs/instance/status/<irs_instance_hostname> - pulls all the IRS cases
* /v1/irs/instance/status/<irs_instance_hostname>?case_id=<id> - shows the status of a given case_id
* /v1/irs/instance/status/<irs_instance_hostname>?status=closed - pulls a list of all closed cases
* /help


# Curl examples

# DEL
Disconnect a node from IRS instance:

```
curl -uirs:cloudtoirs -s -v -X DELETE http://irs_api/v1/irs/node/del/hostname.fqdn.com
```

The same using hpilo_cli command line:
```
hpilo_cli --login=Administrator --password=’$PASS’ iLO_IP disable_ers
```

# ADD
Include a node to be monitored by IRS:
> Note: irs_instance_fqdn being your HP Insight Remote Support Hostname/IP.

```
curl -s -v -H 'Content-Type: application/json' -X POST http://irs_api/v1/irs/node/add/ilo-hostname.fqdn.com --data "{ \"ers_destination_url\": \"irs_instance_fqdn\" }"
```

The same using hpilo_cli:
```
hpilo_cli --login=Administrator --password=$PASS iLO_IP set_ers_irs_connect ers_destination_url=irs_instance_fqdn ers_destination_port=7906
```

# STATUS
Check the status (connected or disconnected)
```
curl -s -v -X GET http://irs_api/v1/irs/node/status/ilo_hostname.fqdn.com
```

The same with hpilo_cli:
```
hpilo_cli --login=Administrator --password=$PASS ilo_hostname.fqdn.com get_ers_settings
```

# IRS Side
- postgresql.conf: listen_addresses = '*'
- pg_hba.conf: host UCA ro_user 0.0.0.0/0 md5
- postgresql or pgadmin: create a ro_user with read-only privileges

and reload postgresql configs

# DOCKER

Docker version:

```
bash build.sh
```

# THANKS - hpilo_cli
- https://github.com/seveas/python-hpilo for providing hpilo library
