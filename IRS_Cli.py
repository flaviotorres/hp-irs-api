#!/opt/ipaas/bin/python
#-*- coding: utf-8; -*-

import os
import sys
import json
import time
import hpilo
import logging
import psycopg2

from functools import wraps, update_wrapper
from werkzeug.routing import BaseConverter
from flask import Flask, jsonify, make_response, request, abort, Response
from flask_json import FlaskJSON, JsonError, json_response, as_json


app = Flask(__name__)
FlaskJSON(app)
FLASK_DEBUG=1

app.config.from_pyfile('config.py')

ilo_username=app.config['ILO_USERNAME']
ilo_password=app.config['ILO_PASSWORD']
ers_destination_port=app.config['ERS_DESTINATION_PORT']
db_username=app.config['DB_USERNAME']
db_password=app.config['DB_PASSWORD']
db_port=app.config['DB_PORT']
irs_database=app.config['IRS_DATABASE']


class RegexConverter(BaseConverter):
    def __init__(self, url_map, *items):
        super(RegexConverter, self).__init__(url_map)
        self.regex = items[0]

app.url_map.converters['regex'] = RegexConverter


logging.basicConfig(
    # docker, redirecting to stdout, not filename
    #filename=app.config['LOG_FILE'],
    format=app.config['LOG_FORMAT'],
    level=logging.DEBUG
)

# basic authentication
def check_auth(username, password):
    return username == 'irs' and password == 'cloudtoirs'

def authenticate():
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated



@app.route('/')
@app.route('/index.html', methods=['GET'])
def index():
	return("<h3><a href='/help'> /help</a> </h3>")

@app.route('/help', methods=['GET'])
def dns_help(name='help'):
    logger = logging.getLogger("dns_help")
    logger.info("help page")
    return """IRS API <a href='https://h20392.www2.hpe.com/portal/swdepot/displayInstallInfo.do?productNumber=REMOTESUPPORT' target='_blank'>HPE IRS</a><br>
	<br>
    <ul>
	<li>/v1/irs/node/status/<hostname> - whether or not a host is registered in IRS</li>
    <li>/v1/irs/node/add/<hostname> - register iLO hostname in IRS</li>
	<li>/v1/irs/node/del/<hostname> - unregister iLO hostname from IRS</li>
    <li>/v1/irs/instance/status/<irs_instance_hostname> - pulls all IRS the cases</li>
    <li>/v1/irs/instance/status/<irs_instance_hostname>?case_id=<id> - shows the status of a given case_id</li>
    <li>/v1/irs/instance/status/<irs_instance_hostname>?status=closed - pulls a list of all closed cases</li>
    <li>/help</li>
    </ul>"""


@app.route('/v1/irs/node/del/<regex("([-a-zA-Z0-9_.]+)"):ilo_ip>', methods=['DELETE'])
@requires_auth
def del_irs(ilo_ip):
    logger = logging.getLogger("del_irs")
    # Basic validation
    if ilo_ip is None:
        abort(404)
    try:
        ilo = hpilo.Ilo(ilo_ip, ilo_username, ilo_password)
        ilo_disable_ers = ilo.disable_ers()
        logger.info("DEL_IRS: User just disconnected %s node from its IRS instance.", ilo_ip)
        return json_response(200, status='success', irs_disable_ers=ilo_disable_ers)
    except Exception as err:
        return json_response(500, status='error', ilo_response=str(err))

@app.route('/v1/irs/node/add/<regex("([-a-zA-Z0-9_.]+)"):ilo_ip>', methods=['POST'])
@requires_auth
def add_irs(ilo_ip):
    logger = logging.getLogger("add_irs")
    data = json.loads(request.data)

    if not 'ers_destination_url' in data:
        abort(400)
    else:
        ers_destination_url = data['ers_destination_url']
        try:
            ilo = hpilo.Ilo(ilo_ip, ilo_username, ilo_password)
            ilo_ers_irs_connect = ilo.set_ers_irs_connect(data['ers_destination_url'],ers_destination_port)
            logger.info("ADD_IRS: User just connected %s node to %s IRS instance.",ilo_ip,ers_destination_url)
            return json_response(200, status='success', ilo_ers_irs_connect=ilo_ers_irs_connect)
        except hpilo.IloError as ilo_error:
            return json_response(500, status='error', ilo_response=str(ilo_error))

@app.route('/v1/irs/node/status/<regex("([-a-zA-Z0-9_.]+)"):ilo_ip>', methods=['GET'])
def node_status_irs(ilo_ip):
    logger = logging.getLogger("node_status_irs")

    try:
        ilo = hpilo.Ilo(ilo_ip, ilo_username, ilo_password)
        ilo_irs_settings = ilo.get_ers_settings()
        logger.info("NODE_STATUS: checking the status of %s", ilo_ip)
        return json_response(200, status='success', irs_settings=ilo_irs_settings)
    except Exception as err:
        return json_response(500, status='error', ilo_response=str(err))


@app.route('/v1/irs/instance/status/<regex("([-a-zA-Z0-9_.]+)"):irs_instance>', methods=['GET'])
def status_irs(irs_instance=None):
    logger = logging.getLogger("status_irs")

    try:
        conn_str="host='%s' dbname='%s' user='%s' password='%s' port='%s'" % (irs_instance,irs_database,db_username,db_password,db_port)
        conn=psycopg2.connect(conn_str)

        cur = conn.cursor()

        try:
            irs_cases = []

            cur.execute("""SELECT grp_id from OOS_GRP where GRP_NM = 'All Devices'""")
            group_id = cur.fetchone()[0]

            query_state_filter = request.args.get('status')
            query_case_id_filter = request.args.get('case_id')

            if query_state_filter and query_state_filter == 'closed':
                # filter by closed states
                logger.info("IRS Tickets: gathering all the cases from %s IRS Instance and filtering by %s state", irs_instance,query_state_filter)
                QUERY = "SELECT s.srvc_evnt_ky, s.sevr, s.prblm_area, s.prblm_dn, s.tm_of_evnt, s.case_id, s.case_stat, s.recmnd_actns, s.integration_msg_uuid, imsg.oos_ky, o.nm, o.physcl_site_ky, pd.prod_mdl, sys.os_nm, (SELECT addr FROM ip_cnfg  JOIN physcl_iface ON (ip_cnfg.physcl_iface_ky = physcl_iface.physcl_iface_ky) WHERE physcl_iface.prod_ky = pd.prod_ky AND ip_cnfg.is_prim = TRUE) AS ipaddress, rel.oos_to as ilokey, sys.hst_nm, o.srl_nr, pd.prod_srl_nr, (SELECT nm FROM oos WHERE oos_ky = rel.oos_to) as iloname, (SELECT cfg.addr FROM oos oo LEFT OUTER JOIN prod ON (oo.oos_ky = prod.oos_ky) LEFT OUTER JOIN physcl_iface pp ON (prod.prod_ky = pp.prod_ky) LEFT OUTER JOIN ip_cnfg cfg ON (cfg.physcl_iface_ky = pp.physcl_iface_ky AND cfg.is_prim = TRUE) WHERE oo.oos_ky = rel.oos_to) as iloipaddress FROM srvc_evnt s LEFT OUTER JOIN integration_msg imsg ON (s.integration_msg_uuid = imsg.integration_msg_uuid) LEFT OUTER JOIN oos o ON (o.oos_ky = imsg.oos_ky) LEFT OUTER JOIN oos_relshp rel ON (imsg.oos_ky = rel.oos_frm AND rel.typ = 2) LEFT OUTER JOIN prod pd ON (o.oos_ky = pd.oos_ky) LEFT OUTER JOIN sys_prod sys ON (sys.prod_ky = pd.prod_ky) WHERE o.oos_ky IN (SELECT oos_ky FROM oos_grp_oos_map WHERE grp_id = '%s') AND s.case_stat = 'closed' ORDER BY s.tm_of_evnt desc OFFSET '0'" % group_id
            elif query_case_id_filter:
                logger.info("IRS Tickets: gathering all the cases from %s IRS Instance filtering by case_id number %s", irs_instance,query_case_id_filter)
                # filter by case_id
                QUERY = "SELECT s.srvc_evnt_ky, s.sevr, s.prblm_area, s.prblm_dn, s.tm_of_evnt, s.case_id, s.case_stat, s.recmnd_actns, s.integration_msg_uuid, imsg.oos_ky, o.nm, o.physcl_site_ky, pd.prod_mdl, sys.os_nm, (SELECT addr FROM ip_cnfg  JOIN physcl_iface ON (ip_cnfg.physcl_iface_ky = physcl_iface.physcl_iface_ky) WHERE physcl_iface.prod_ky = pd.prod_ky AND ip_cnfg.is_prim = TRUE) AS ipaddress, rel.oos_to as ilokey, sys.hst_nm, o.srl_nr, pd.prod_srl_nr, (SELECT nm FROM oos WHERE oos_ky = rel.oos_to) as iloname, (SELECT cfg.addr FROM oos oo LEFT OUTER JOIN prod ON (oo.oos_ky = prod.oos_ky) LEFT OUTER JOIN physcl_iface pp ON (prod.prod_ky = pp.prod_ky) LEFT OUTER JOIN ip_cnfg cfg ON (cfg.physcl_iface_ky = pp.physcl_iface_ky AND cfg.is_prim = TRUE) WHERE oo.oos_ky = rel.oos_to) as iloipaddress FROM srvc_evnt s LEFT OUTER JOIN integration_msg imsg ON (s.integration_msg_uuid = imsg.integration_msg_uuid) LEFT OUTER JOIN oos o ON (o.oos_ky = imsg.oos_ky) LEFT OUTER JOIN oos_relshp rel ON (imsg.oos_ky = rel.oos_frm AND rel.typ = 2) LEFT OUTER JOIN prod pd ON (o.oos_ky = pd.oos_ky) LEFT OUTER JOIN sys_prod sys ON (sys.prod_ky = pd.prod_ky) WHERE o.oos_ky IN (SELECT oos_ky FROM oos_grp_oos_map WHERE grp_id = '%s') AND s.case_id = '%s' ORDER BY s.tm_of_evnt desc OFFSET '0'" % (group_id,query_case_id_filter)
            else:
                # bring all
                logger.info("IRS Tickets: gathering all the cases from %s IRS Instance, no filter applied", irs_instance)
                QUERY = "SELECT s.srvc_evnt_ky, s.sevr, s.prblm_area, s.prblm_dn, s.tm_of_evnt, s.case_id, s.case_stat, s.recmnd_actns, s.integration_msg_uuid, imsg.oos_ky, o.nm, o.physcl_site_ky, pd.prod_mdl, sys.os_nm, (SELECT addr FROM ip_cnfg  JOIN physcl_iface ON (ip_cnfg.physcl_iface_ky = physcl_iface.physcl_iface_ky) WHERE physcl_iface.prod_ky = pd.prod_ky AND ip_cnfg.is_prim = TRUE) AS ipaddress, rel.oos_to as ilokey, sys.hst_nm, o.srl_nr, pd.prod_srl_nr, (SELECT nm FROM oos WHERE oos_ky = rel.oos_to) as iloname, (SELECT cfg.addr FROM oos oo LEFT OUTER JOIN prod ON (oo.oos_ky = prod.oos_ky) LEFT OUTER JOIN physcl_iface pp ON (prod.prod_ky = pp.prod_ky) LEFT OUTER JOIN ip_cnfg cfg ON (cfg.physcl_iface_ky = pp.physcl_iface_ky AND cfg.is_prim = TRUE) WHERE oo.oos_ky = rel.oos_to) as iloipaddress FROM srvc_evnt s LEFT OUTER JOIN integration_msg imsg ON (s.integration_msg_uuid = imsg.integration_msg_uuid) LEFT OUTER JOIN oos o ON (o.oos_ky = imsg.oos_ky) LEFT OUTER JOIN oos_relshp rel ON (imsg.oos_ky = rel.oos_frm AND rel.typ = 2) LEFT OUTER JOIN prod pd ON (o.oos_ky = pd.oos_ky) LEFT OUTER JOIN sys_prod sys ON (sys.prod_ky = pd.prod_ky) WHERE o.oos_ky IN (SELECT oos_ky FROM oos_grp_oos_map WHERE grp_id = '%s') ORDER BY s.tm_of_evnt desc OFFSET '0'" % group_id

            cur.execute(QUERY)

            for row in cur.fetchall():
                srvc_evnt_ky, sevr, prblm_area, prblm_dn, tm_of_evnt, case_id, case_stat, recmnd_actns, integration_msg_uuid, oos_ky, nm, physcl_site_ky, prod_mdl, os_nm, ipaddress, ilokey, hst_nm, srl_nr, prod_srl_nr, iloname, iloipaddress = row
                irs_cases.append({"srvc_evnt_ky": srvc_evnt_ky,
                                    "sevr": sevr,
                                    "prblm_area": prblm_area,
                                    "prblm_dn": prblm_dn,
                                    "tm_of_evnt": tm_of_evnt,
                                    "case_id": case_id,
                                    "case_stat": case_stat,
                                    "recmnd_actns": recmnd_actns,
                                    "integration_msg_uuid": integration_msg_uuid,
                                    "oos_ky": oos_ky,
                                    "nm": nm,
                                    "physcl_site_ky": physcl_site_ky,
                                    "prod_mdl": prod_mdl,
                                    "os_nm": os_nm,
                                    "ipaddress": ipaddress,
                                    "ilokey": ilokey,
                                    "hst_nm": hst_nm,
                                    "srl_nr": srl_nr,
                                    "prod_srl_nr": prod_srl_nr,
                                    "iloname": iloname,
                                    "iloipaddress": iloipaddress})

            cur.close()


            return json_response(200, status='success', irs_cases=irs_cases)

        except Exception as err:
            print ("err %s" % err)

    except Exception as err:
        return json_response(500, status='error', response=str(err))



# ERROR HANDLERS
@app.errorhandler(404)
def not_found(error):
    return make_response(
        jsonify({
                'status': 'error',
                'msg': 'Not found'
        }),
        404
    )

@app.errorhandler(400)
def bad_request(error):
    return make_response(
        jsonify({
            'status': 'error',
            'msg': 'Bad Request'
        }),
        404
    )

@app.errorhandler(500)
def error_request(error):
    return make_response(
        jsonify({
            'status': 'error',
            'msg': 'Internal Server Error'
        }),
        400
    )

if __name__ == "__main__":
    app.run(host = '0.0.0.0',port=5000)
