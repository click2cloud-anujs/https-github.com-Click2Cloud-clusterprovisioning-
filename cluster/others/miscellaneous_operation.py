import base64
import json
import os
import time

import requests
from django.db import connection
from idna import unicode

from clusterProvisioningClient.settings import BASE_DIR, decrypt_credentials_api_endpoint

config_dumps_path = os.path.join(BASE_DIR, 'config_dumps')

AZURE_CLOUD = 'azure'
ALIBABA_CLOUD = 'alibaba'
OTC_CLOUD = 'otc'
AWS_CLOUD = 'ec2'
GCP_CLOUD = 'gce'
OPENSTACK_CLOUD = 'openstack'


def get_access_key_secret_key_list(user_id, cloud_type):
    """
    retrieve the list of access keys and secrete keys from db
    :param cloud_type:
    :param user_id:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        # create cursor for calling stored procedure
        cursor = connection.cursor()
        cmd = "SELECT public._cb_cp_sp_access_key_secret_key('%s','%s')" % (user_id, cloud_type)
        cursor.execute(cmd)
        rows = cursor.fetchall()
        result = rows[0][0]
        response = json.dumps(result)
        if result is None:
            error = True
            response = 'Invalid user_id or no data available.'
        elif len(result) > 0:
            headers = {'content-type': 'application/json'}
            # Calling node js api for decrypting the alibaba encrypted access keys and secret keys
            result_api = requests.post(url=decrypt_credentials_api_endpoint, data=response, headers=headers)
            if result_api.status_code != 200:
                raise Exception('Failed to decrypt the credentials.')
            result_api = json.loads(result_api.content)
            if result_api.get('is_successful'):
                response = result_api.get('credentials')
            else:
                error = True
                response = result_api.get('error')
                if not result_api.get('error'):
                    print(result_api.get('error'))
                    raise Exception('Failed to decrypt the credentials.')

    except Exception as e:
        error = True
        if 'Failed to decrypt' in e.message:
            response = e.message
        elif "/api/v1/decryptCredentials" in str(e):
            response = "Facing issues while connecting middleware"
        elif os.getenv("DB_Host") in e.message:
            response = 'Cannot connect to Database server'
        else:
            response = e.message
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def key_validations_cluster_provisioning(request_keys, validation_keys):
    """
    validate the keys from request parameter
    :param request_keys: keys received from request which need to validate
    :param validation_keys: referenced keys for validation
    :return:
    """
    response = {}
    missing_key_flag = False
    missing_value_flag = False
    try:
        missing_keys = []
        missing_values = []
        for key in validation_keys:
            if key not in request_keys:
                missing_key_flag = True
                missing_keys.append(key)
            elif key in ['provider_id', 'user_id', 'webhook_id']:
                # checking the type of value is int only
                if not isinstance(request_keys.get(key), int):
                    missing_value_flag = True
                    missing_values.append(key)
            elif key in ['region_id', 'cluster_id', 'application_body', 'name', 'namespace', 'application_name',
                         'cluster_config', 'cluster_name', 'repository_name', 'repository_summary',
                         'repository_detail', 'repository_type', 'webhook_name', 'webhook_url', 'trigger_type',
                         'tag_name']:
                # checking string length and checking the type of value is string only
                if (len(str(request_keys.get(key)).strip())) == 0 or not isinstance(request_keys.get(key), unicode):
                    missing_value_flag = True
                    missing_values.append(key)
            elif key in ['request_body', 'build_config', 'deployment_config']:
                # checking dict length and checking the type of value is dict only
                if not isinstance(request_keys.get(key), dict) or len(request_keys.get(key)) == 0:
                    missing_value_flag = True
                    missing_values.append(key)
            elif key in ['zone_id_list', 'trigger_tag_list']:
                # checking dict length and checking the type of value is dict only
                if not isinstance(request_keys.get(key), list) or len(request_keys.get(key)) == 0:
                    missing_value_flag = True
                    missing_values.append(key)

        if missing_key_flag or missing_value_flag:
            response = {
                'error':
                    {
                        'message': 'Following keys and/or values are missing in request parameter or value type is invalid.',
                        'keys_info': {
                            'keys': missing_keys,
                            'values': missing_values,
                        }
                    }
            }
            if len(missing_keys) == 0 and len(missing_values) == 0:
                response.get('error').get('keys_info').update({'keys': []})
                response.get('error').get('keys_info').update({'values': []})
            elif len(missing_keys) == 0:
                response.get('error').get('keys_info').update({'keys': []})
            elif len(missing_keys) == 0:
                response.get('error').get('missing').update({'values': []})
    except Exception as e:
        error = True
        response.update({
            'message': e.message
        })
        print(e.message)
    finally:
        if len(response) == 0:
            # return error=False if response is empty
            error = False
            return error, response
        else:
            # return error=True if response is not empty
            error = True
            return error, response


def insert_or_update_cluster_details(params):
    """
    insert or update the cluster details in the database
    :param params:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        user_id = int(params.get('user_id'))
        provider_id = int(params.get('provider_id'))
        cluster_id = str(params.get('cluster_id'))
        a = params.get('cluster_details')
        print(a)
        # cluster_details = str(base64.b64encode(params.get('cluster_details')))
        cluster_details = params.get('cluster_details')
        print(cluster_details)
        status = params.get('status')
        operation = params.get('operation')
        if params.get('is_insert'):
            created_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            cmd = "INSERT INTO public._cb_cp_cluster_details(user_id, provider_id, cluster_id, cluster_details, " \
                  "status, created_at, operation) VALUES ({user_id},{provider_id},'{cluster_id}','{cluster_details}'" \
                  ",'{status}','{created_at}','{operation}')".format(
                user_id=int(user_id), provider_id=int(provider_id),
                cluster_id=cluster_id,
                cluster_details=cluster_details,
                status=status, created_at=created_at,
                operation=operation)
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
        else:
            # update operation
            cmd = "UPDATE public._cb_cp_cluster_details SET status = '{status}', cluster_details = " \
                  "'{cluster_details}', operation = '{operation}' " \
                  "where user_id = {user_id} and provider_id = {provider_id} and cluster_id = '{cluster_id}' ".format(
                status=status,
                cluster_details=cluster_details,
                operation=operation,
                user_id=user_id,
                provider_id=provider_id,
                cluster_id=cluster_id
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def insert_or_update_namespace_details(params):
    """
    insert or update the namespace details in the database
    :param params:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        user_id = int(params.get('user_id'))
        provider_id = int(params.get('provider_id'))
        namespace_id = str(params.get('namespace_id'))
        namespace_details = str(base64.b64encode(json.dumps(params.get('namespace_details'))))
        status = params.get('status')
        operation = params.get('operation')
        if params.get('is_insert'):
            created_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            cmd = "INSERT INTO public._cb_cr_namespace_details(user_id, provider_id, namespace_id, namespace_details, " \
                  "status, created_at, operation) VALUES ({user_id},{provider_id},'{namespace_id}','{namespace_details}'" \
                  ",'{status}','{created_at}','{operation}')".format(
                user_id=int(user_id), provider_id=int(provider_id),
                namespace_id=namespace_id,
                namespace_details=namespace_details,
                status=status, created_at=created_at,
                operation=operation)
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
        else:
            # update operation
            cmd = "UPDATE public._cb_cr_namespace_details SET status = '{status}', namespace_details = " \
                  "'{namespace_details}', operation = '{operation}' " \
                  "where user_id = {user_id} and provider_id = {provider_id} and namespace_id = '{namespace_id}' ".format(
                status=status,
                namespace_details=namespace_details,
                operation=operation,
                user_id=user_id,
                provider_id=provider_id,
                namespace_id=namespace_id
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def insert_or_update_repository_details(params):
    """
    insert or update the repository details in the database
    :param params:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        user_id = int(params.get('user_id'))
        provider_id = int(params.get('provider_id'))
        repository_id = str(params.get('repository_id'))
        repository_details = str(base64.b64encode(json.dumps(params.get('repository_details'))))
        status = params.get('status')
        operation = params.get('operation')
        if params.get('is_insert'):
            created_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            cmd = "INSERT INTO public._cb_cr_repository_details(user_id, provider_id, repository_id, repository_details, " \
                  "status, created_at, operation) VALUES ({user_id},{provider_id},'{repository_id}','{repository_details}'" \
                  ",'{status}','{created_at}','{operation}')".format(
                user_id=int(user_id), provider_id=int(provider_id),
                repository_id=repository_id,
                repository_details=repository_details,
                status=status, created_at=created_at,
                operation=operation)
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
        else:
            # update operation
            cmd = "UPDATE public._cb_cr_repository_details SET status = '{status}', repository_details = " \
                  "'{repository_details}', operation = '{operation}' " \
                  "where user_id = {user_id} and provider_id = {provider_id} and repository_id = '{repository_id}' ".format(
                status=status,
                repository_details=repository_details,
                operation=operation,
                user_id=user_id,
                provider_id=provider_id,
                repository_id=repository_id
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def insert_or_update_s2i_details(params, insert_unique_id=None):
    """
    insert or update the s2i details in the database
    :param params:
    :param insert_unique_id:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        user_id = int(params.get('user_id'))
        status = params.get('status')
        comment = params.get('comment')
        tag = params.get('tag')
        new_image_name = params.get('image_name')
        print('comment = %s for new_image_name = %s' % (comment, new_image_name))
        if params.get('is_insert'):
            github_url = params.get('github_url')
            builder_image = params.get('builder_image')
            registry = params.get('registry')
            created_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            cmd = "INSERT INTO public._cb_cp_s2i_details(user_id, created_at, image, builder_image, " \
                  "github_url, tag, status, comment, registry) VALUES ({user_id},'{created_at}','{image}','{builder_image}'" \
                  ",'{github_url}','{tag}','{status}','{comment}','{registry}') RETURNING id".format(
                user_id=int(user_id),
                created_at=created_at,
                image=new_image_name,
                builder_image=builder_image, github_url=github_url,
                tag=tag,
                status=status,
                comment=comment,
                registry=registry)
            cursor.execute(cmd)
            response = cursor.fetchall()
        else:
            # update operation
            build_complete_status = "UPDATE public._cb_cp_s2i_details SET status = '{status}', comment = " \
                                    "'{comment}'" \
                                    "where id = {id} and user_id = {user_id} and image = '{image}' and tag = '{tag}' ".format(
                status=status,
                comment=comment,
                id=insert_unique_id,
                user_id=user_id,
                image=new_image_name,
                tag=tag,
            )
            cursor.execute(build_complete_status)
            connection.commit()
            response = 'Success'
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return response, error


def get_db_info_using_cluster_id(cluster_id=None):
    """
    retrieve the data of cluster from db
    :param cluster_id:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        sql_cmd = "SELECT * FROM public._cb_cp_cluster_details where cluster_id = '{cluster_id}'".format(
            cluster_id=cluster_id)
        cursor.execute(sql_cmd)
        response = cursor.fetchall()
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def get_db_info_using_provider_id(provider_id):
    """
    retrieve the data of cluster from db
    :param provider_id:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        sql_cmd = "SELECT * FROM public._cb_cp_cluster_details where provider_id = '{provider_id}'".format(
            provider_id=provider_id)
        cursor.execute(sql_cmd)
        response = cursor.fetchall()
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def get_db_info_using_user_id_and_provider_id(user_id, provider_id):
    """
    retrieve the data of cluster from db
    :param user_id:
    :param provider_id:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        sql_cmd = "SELECT * FROM public._cb_cp_cluster_details where user_id = {user_id} and provider_id = {provider_id}".format(
            user_id=user_id, provider_id=provider_id)
        cursor.execute(sql_cmd)
        response = cursor.fetchall()
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def get_s2i_details(user_id):
    """
    retrieve the data of s2i images from db
    :param user_id:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()

        sql_cmd = "SELECT * FROM public._cb_cp_s2i_details where user_id = '{user_id}'".format(
            user_id=user_id)
        cursor.execute(sql_cmd)
        response = cursor.fetchall()
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def delete_s2i_image_detail_from_db(json_request):
    """
    delete s2i detail from database
    :param json_request:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()

        sql_cmd = "DELETE FROM public._cb_cp_s2i_details where user_id = '{user_id}' and image = '{image_name}' " \
                  "and builder_image = '{builder_image}' and tag = '{tag}' and created_at = '{created_at}' and " \
                  "registry ='{registry}' and github_url = '{github_url}'".format(
            user_id=json_request.get('user_id'),
            image_name=json_request.get('image_name'),
            builder_image=json_request.get('builder_image'),
            tag=json_request.get('tag'),
            created_at=json_request.get('created_at'),
            registry=json_request.get('registry'),
            github_url=json_request.get('github_url'))

        cursor.execute(sql_cmd)
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def create_cluster_config_file(cluster_id, config_details):
    """
    create the folder for the config file of kubernetes cluster with its id as a directory name
    :param cluster_id:
    :param config_details:
    :return:
    """
    error = False
    response = None
    try:
        path = os.path.join(config_dumps_path, cluster_id)
        if not os.path.exists(path):
            os.makedirs(path)
        path = os.path.join(path, 'config')
        if not os.path.exists(path):
            with open(path, 'w+') as outfile:
                json.dump(config_details, outfile)
    except Exception as e:
        error = True
        response = e.message
        print(e.message)
    finally:
        return error, response


def get_grouped_credential_list(credentials):
    """
    groups the common credentials according to the access key
    :param credentials:
    :return:
    """
    error = False
    response = None
    try:
        # credentials = json.loads(credentials)
        credential_list = []
        unique_access_keys = set(item.get('client_id') for item in credentials)
        for access_key in unique_access_keys:
            provider_name_list = []
            credential_json = {}
            secret_key = None
            subscription_id = None
            tenant_id = None
            for element in credentials:
                if element.get('client_id') == access_key:
                    provider_name_list.append({
                        'name': element.get('name'),
                        'id': element.get('id')
                    })
                    subscription_id = element.get('subscription_id')
                    tenant_id = element.get('tenant_id')
                    secret_key = element.get('client_secret')
            credential_json.update({
                'provider_name_list': provider_name_list,
                'access_key': access_key,
                'secret_key': secret_key,
                'tenant_id': tenant_id,
                'subscription_id': subscription_id
            })
            credential_list.append(credential_json)
        response = credential_list
    except Exception as e:
        error = True
        response = e.message
        print(e.message)
    finally:
        return error, response


def check_for_provider_id(provider_id, credentials):
    """
    checks for the provider_id present in credentials
    :param provider_id:
    :param credentials:
    :return:
    """
    error = False
    response = None
    try:
        # credentials = json.loads(credentials)
        for item in credentials:
            if item.get('id') == provider_id:
                error = False
                response = item
                break
            else:
                error = True
        if error:
            response = 'provider does not exists'
    except Exception as e:
        error = True
        response = e.message
        print(e.message)
    finally:
        return error, response


def insert_or_update_cluster_config_details(params):
    """
    insert or update the cluster details in the database
    :param params:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        provider = str(params.get('provider'))
        cluster_id = str(params.get('cluster_id'))
        cluster_public_endpoint = str(params.get('cluster_public_endpoint'))
        cluster_config = str(base64.b64encode(str(params.get('cluster_config'))))
        cluster_token = str(base64.b64encode(params.get('cluster_token').encode("utf-8")))
        if params.get('is_insert'):
            cmd = "INSERT INTO public._cb_cp_cluster_config_details(provider, cluster_id, cluster_public_endpoint, " \
                  "cluster_config, cluster_token) VALUES ('{provider}','{cluster_id}','{cluster_public_endpoint}','{cluster_config}'" \
                  ",'{cluster_token}')".format(
                provider=provider, cluster_id=str(cluster_id),
                cluster_public_endpoint=cluster_public_endpoint,
                cluster_config=cluster_config,
                cluster_token=cluster_token
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
        else:
            # update operation
            cmd = "UPDATE public._cb_cp_cluster_config_details SET cluster_config = '{cluster_config}', cluster_token = " \
                  "'{cluster_token}' where provider = '{provider}' and cluster_id = '{cluster_id}'".format(
                cluster_config=cluster_config,
                cluster_token=cluster_token,
                provider=provider,
                cluster_id=cluster_id
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def get_cluster_config_details(provider, cluster_id):
    """
    retrieve the data of s2i images from db
    :param provider:
    :param cluster_id:
    :return:
    """
    cursor = None
    error = False
    cluster_config_details = {}
    response = None
    try:
        cursor = connection.cursor()
        sql_cmd = "SELECT cluster_public_endpoint, cluster_config, cluster_token FROM " \
                  "public._cb_cp_cluster_config_details where provider = " \
                  "'{provider}' and cluster_id = '{cluster_id}'".format(
            provider=provider,
            cluster_id=cluster_id)
        cursor.execute(sql_cmd)
        result = cursor.fetchall()
        if len(result) > 0:
            result = result[0]
            cluster_config = base64.b64decode(bytes(str(result[1])))
            cluster_token = str(result[2])
            cluster_token = base64.b64decode(bytes(cluster_token))
            cluster_config_details.update({
                'cluster_public_endpoint': result[0],
                'cluster_config': cluster_config,
                'cluster_token': cluster_token
            })
        response = cluster_config_details

    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def run_postgres_sql_script():
    """
    Creates tables and stored procedures in postgres database if not exist
    """
    cursor = None
    try:
        postgres_sql_cluster_provisioning_tables_file = os.path.join(BASE_DIR, 'dependency', 'database', 'tables.sql')
        postgres_sql_cluster_provisioning_stored_procedures_file = os.path.join(BASE_DIR, 'dependency', 'database',
                                                                                'stored_procedures.sql')
        print("Database script executing")
        # create cursor for calling stored procedure
        cursor = connection.cursor()
        # create cluster provisioning related tables if not exist
        postgres_sql_cluster_provisioning_tables_file_string = open(str(postgres_sql_cluster_provisioning_tables_file),
                                                                    "r").read()
        cursor.execute(postgres_sql_cluster_provisioning_tables_file_string)

        # create cluster provisioning related functions
        postgres_sql_cluster_provisioning_stored_procedures_file_string = open(
            str(postgres_sql_cluster_provisioning_stored_procedures_file), "r").read()
        cursor.execute(postgres_sql_cluster_provisioning_stored_procedures_file_string)
        connection.commit()
        print("Database script execution completed")
    except Exception as e:
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()


def clean_instance_type_details():
    cursor = None
    try:
        print("Clearing instance list for Alibaba")
        # create cursor for calling stored procedure
        cursor = connection.cursor()

        # create cluster provisioning related functions
        cmd = 'delete FROM public._cb_cp_instance_details where id > 0;'
        cursor.execute(cmd)
        connection.commit()
        print("Clearing instance list for Alibaba is completed")
    except Exception as e:
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()


def get_instance_details(provider_name, zone_id):
    """
    retrieve the data of instance type by zone_id
    :param provider_name:
    :param zone_id:
    :return:
    """
    cursor = None
    error = False
    instance_type_details = {}
    response = None
    try:
        cursor = connection.cursor()
        sql_cmd = "SELECT instance_details FROM public._cb_cp_instance_details where cloud_provider = " \
                  "'{provider_name}' and zone_id = '{zone_id}'".format(
            provider_name=provider_name,
            zone_id=zone_id)
        cursor.execute(sql_cmd)
        result = cursor.fetchall()
        if len(result) > 0:
            result = result[0]
            instance_type_details = (result[0])
        response = instance_type_details

    except Exception as e:
        error = True
        response = e.message
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response


def insert_or_update_instance_details(params):
    """
    insert or update instance type data of instance type by zone_id and provider_name
    :param params:
    :return:
    """
    cursor = None
    error = False
    response = None
    try:
        cursor = connection.cursor()
        instance_details = json.dumps({"instance_type_list": params.get('instance_details')})
        provider_name = str(params.get('provider_name'))
        zone_id = str(params.get('zone_id'))
        error_get_instance_details, response_get_instance_details = get_instance_details(provider_name, zone_id)
        if not error_get_instance_details:
            if len(response_get_instance_details) > 0:
                params.update({'is_insert': False})
        else:
            raise Exception(response_get_instance_details)
        if params.get('is_insert'):
            cmd = "INSERT INTO public._cb_cp_instance_details(cloud_provider, zone_id, instance_details)" \
                  " VALUES ('{cloud_provider}','{zone_id}','{instance_details}');".format(
                cloud_provider=provider_name, zone_id=str(zone_id),
                instance_details=instance_details
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
        else:
            # update operation
            cmd = "UPDATE public._cb_cp_instance_details SET instance_details = '{instance_details}' " \
                  "where cloud_provider = '{cloud_provider}' and zone_id = '{zone_id}'".format(
                cloud_provider=provider_name, zone_id=str(zone_id),
                instance_details=instance_details
            )
            cursor.execute(cmd)
            connection.commit()
            response = 'Success'
    except Exception as e:
        error = True
        response = 'Cannot connect to Database server'
        print(e.message)
    finally:
        if cursor is not None:
            cursor.close()
        return error, response
