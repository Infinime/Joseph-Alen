from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from .models import Location, Task

def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        next_url = request.POST.get("next")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(next_url or "/")
        else:
            # Add an error message if login fails
            return render(request, "login.html", {"error": "Invalid credentials"})

    return render(request, "login.html")


def signup_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/")
    else:
        form = UserCreationForm()
    return render(request, "signup.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def index(request, sample=7):
    today = date.today()
    formatted_date = today.strftime("Today: %A, %B %d, %Y")
    due_next = {}
    for location in request.user.locations.all():
        due_next[str(location)] = location.due_next(sample)

    context = {
        "today_date": formatted_date,
        "sample": sample,
        "today": today,
        "dates": (dates:=[today + timedelta(_) for _ in range(0, sample)]),
        "dates_str": [day.strftime('%Y-%m-%d') for day in dates],
        "due_next": due_next,
        "next_decade": [today.year+i for i in range(10)],
        "months": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
        "weekdays":["Sunday","Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    }
    return render(request, "base.html", context)



@require_POST
def yearly_tasks(request):
    # Yearly tasks per location
    data = json.loads(request.body)
    year = data.get('year')
    location_id = data.get('location_id')
    location = Location.objects.get(id=location_id)
    tasks = location.this_year_tasks(year)

    return JsonResponse({'tasks': tasks, "length":len(tasks)})

def get_next_available_day(request, year_view: dict, year: int, month: int, day: int):
    user = request.user.user_profile
    while True:
        day += 1
        if day > year_view[month]['days_in_month']:
            day = 1
            month += 1
            if month > 12:
                return None, None
        # Check if the current day is not Saturday (5) or Sunday (6)
        availability = user.availability.get(f"{year}-{month:02d}-{day:02d}", 0)
        current_date = date(year, month, day)
        if current_date.weekday() < 5 and sum(task['time_taken'] for task in year_view[month].get(day, {}).values()) < 8 + availability:
            return month, day
def task_list_week(request):
    date_str = request.GET.get('date')
    # Convert the date string to a date object
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    # Calculate the start and end dates of the week containing that date
    start_of_week = date_obj - timedelta(days=date_obj.weekday()+1)
    end_of_week = start_of_week + timedelta(days=6)

    tasks = request.user.tasks.filter(due_date__gt=date_obj).filter(due_date__lte=end_of_week)
    [task.next_occurrence() for task in tasks]
    task_list = [{'name': task.name,
                  'time_taken': task.completion_hrs,
                  "location": task.location.name,
                  "due_date": task.due_date.strftime('%Y-%m-%d'),
                  "id": task.id,
                } for task in tasks]
    return JsonResponse(task_list, safe=False)

def all_yearly_tasks(request):
    data = json.loads(request.body)
    year = data.get("year")
    filt = data.get("filter", {})
    year_view = {month: {"days_in_month": 31 if month in [1, 3, 5, 7, 8, 10, 12] else 30 if month in [4, 6, 9, 11] else 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28} for month in range(1, 13)}
    year_view.update({"year":year, "unique_locations":[], "unique_tasks":{}})
    tasks = request.user.tasks.all()
    if filt:
        tasks = tasks.filter(**filt)
    unique_locations = list(set(task.location.name for task in tasks))
    unique_tasks = {}
    for task in tasks:
        if task.name not in unique_tasks:
            unique_tasks[task.name] = []
        unique_tasks[task.name].append(task.id)
    year_view["unique_locations"] = unique_locations
    year_view["unique_tasks"] = unique_tasks

    for task in tasks:
        task_occurrences = task.all_task_occurences(year)
        for month in task_occurrences:
            days = task_occurrences[month]
            for i, day_str in enumerate(days):
                day = datetime.strptime(day_str, "%Y-%m-%d").day

                date_str = f"{year}-{month:02d}-{day:02d}"
                user_availability = request.user.user_profile.availability.get(date_str, 0)
                current_hours = sum(t['time_taken'] for t in year_view[month].get(day, {}).values())

                # Clip availability to ensure total hours don't exceed 0<=total<=8
                max_available_hours = 8 - current_hours
                clipped_availability = max(0, min(user_availability, max_available_hours))
                # update user availability
                request.user.user_profile.availability[date_str] = clipped_availability
                request.user.user_profile.save()

                if current_hours + task.completion_hrs > 8:
                    # Find the next available day
                    month, day = get_next_available_day(request, year_view, year, month, day)
                    if not (month and day):
                        break

                if day not in year_view[month]:
                    year_view[month][day] = {1: task.json()}
                else:
                    daily_tasks = year_view[month][day]
                    day_arr = list(daily_tasks.values()) + [task.json()]
                    day_arr.sort(key=lambda x: x["location"])
                    year_view[month][day] = {_+1: daym for _, daym in enumerate(day_arr)}


    return JsonResponse(year_view)


@require_POST
def add_availability(request):
    if request.method == 'POST':
        date = request.POST.get('date')
        hours = int(request.POST.get('hours'))
        task_list = request.POST.getlist('task_list')

        # Update user's availability
        user_profile = request.user.user_profile
        availability = dict(user_profile.availability)
        availability[date] = availability.get(date, 0) + hours
        user_profile.availability = availability
        user_profile.save()

        # Move tasks to the selected date
        for task_id in task_list:
            task = Task.objects.get(id=task_id)
            task.due_date = datetime.strptime(date, '%Y-%m-%d').date()
            task.save()

        return redirect('home')
    return JsonResponse({'status': 'error'}, status=400)

@require_POST
def remove_availability(request):
    if request.method == 'POST':
        date_str = request.POST.get('date')
        hours = int(request.POST.get('hours'))
        task_list = request.POST.getlist('remove_task_list')

        # Update user's availability
        user_profile = request.user.user_profile
        availability = user_profile.availability
        availability[date_str] = availability.get(date_str, 0) - hours
        user_profile.availability = availability
        user_profile.save()

        # Construct year_view on the fly
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        year = date_obj.year
        year_view = {month: {"days_in_month": 31 if month in [1, 3, 5, 7, 8, 10, 12] else 30 if month in [4, 6, 9, 11] else 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28} for month in range(1, 13)}
        

        # Populate year_view with tasks
        for task in request.user.tasks.filter(due_date__year=year):
            month = task.due_date.month
            day = task.due_date.day
            if day not in year_view[month]:
                year_view[month][day] = {1: task.json()}
            else:
                daily_tasks = year_view[month][day]
                day_arr = list(daily_tasks.values()) + [task.json()]
                day_arr.sort(key=lambda x: x["location"])
                year_view[month][day] = {_+1: daym for _, daym in enumerate(day_arr)}

        # Move tasks to the next available day
        for task_id in task_list:
            task = Task.objects.get(id=task_id)
            current_month = date_obj.month
            current_day = date_obj.day
            next_month, next_day = get_next_available_day(request, year_view, year, current_month, current_day)
            if next_month and next_day:
                next_available_date = date(year, next_month, next_day)
                task.due_date = next_available_date
                task.save()

        return redirect('home')
    return JsonResponse({'status': 'error'}, status=400)

@require_POST
def move_task(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        task_id = int(data.get('task_id'))
        new_date = data.get('new_date')

        try:
            task = Task.objects.get(id=task_id, user=request.user)
            new_date_obj = datetime.strptime(new_date, '%Y-%m-%d').date()

            task.due_date = new_date_obj

            # Call next_occurrence() method
            task.next_occurrence()
            task.save()

            return JsonResponse({'status': 'success'})
        except Task.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Task not found'}, status=404)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid date format'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

