"""
URL configuration for tasktracker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from tasks import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.index, name='home'),
    path('&sample=<int:sample>/', views.index, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('yearly_tasks/', views.yearly_tasks, name='yearly_tasks'),
    path('yearly_tasks/all', views.all_yearly_tasks, name='all_yearly_tasks'),
    path('availability/add', views.add_availability, name='add_availability'),
    path('availability/remove', views.remove_availability, name='remove_availability'),
    path('task_list_week/', views.task_list_week, name='task_list_week'),
    path("move_task", views.move_task, name='move_task'),
]