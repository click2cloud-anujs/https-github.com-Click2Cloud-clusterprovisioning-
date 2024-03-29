"""clusterProvisioningClient URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin

from cluster.others.miscellaneous_operation import run_postgres_sql_script

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^api/common/', include('common.urls')),
    url(r'^cluster-provisioning/', include('cluster_provisioning.urls')),
    url(r'^cluster-provisioning/', include('source_to_image.urls')),
    url(r'^container-registry-provisioning/', include('registry_provisioning.urls'))

]

run_postgres_sql_script()
