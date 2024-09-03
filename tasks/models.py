from datetime import date, timedelta, datetime
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
    availability = models.JSONField()
    safety_buffer_days = models.IntegerField(default=0)
    show_tooltip = models.BooleanField(default=True)

    def __str__(self):
        return self.user.username


class Task(models.Model):
    name = models.CharField(max_length=200)
    frequency = models.IntegerField()
    completion_hrs = models.IntegerField()
    due_date = models.DateField()
    buffered_date = models.DateField(blank=True, null=True)
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='tasks')
    location = models.ForeignKey('Location', on_delete=models.CASCADE, related_name='tasks')

    def save(self, *args, **kwargs):
        if not self.buffered_date:
            if self.user.user_profile.safety_buffer_days:
                self.buffered_date = self.due_date - timedelta(days=self.user.user_profile.safety_buffer_days)
        super().save(*args, **kwargs)

    def next_occurrence(self):
        today = date.today()
        next_date = self.due_date

        while next_date <= today:
            next_date += timedelta(days=self.frequency)
        # if the next occurence is on a weekend, move it to the next monday
        if next_date.weekday() >= 5:
            next_date += timedelta(days=7 - next_date.weekday())
    
        # Check for task clashes and move to the next day if total hours exceed 8
        while True:
            tasks_on_date = Task.objects.filter(buffered_date=next_date - timedelta(days=self.user.user_profile.safety_buffer_days)).exclude(id=self.id)
            tasks_by_location = {}
            for task in tasks_on_date:
                if task.location not in tasks_by_location:
                    tasks_by_location[task.location] = []
                tasks_by_location[task.location].append(task)
        
            try:
                user_availability = self.user.user_profile.availability[(next_date - timedelta(days=self.user.user_profile.safety_buffer_days)).strftime("%Y-%m-%d")]
            except KeyError:
                user_availability = 0

            total_hours = sum(sum(task.completion_hrs for task in tasks) for tasks in tasks_by_location.values()) + self.completion_hrs + 1.5 - user_availability
        
            if total_hours <= 8:
                break
        
            # Check if this task is lone (no other tasks in the same location on this date)
            if self.location not in tasks_by_location or len(tasks_by_location[self.location]) == 1:
                # This task is lone, so we'll try to pair it with tasks from the same location within the week
                week_start = next_date - timedelta(days=next_date.weekday())
                week_end = week_start + timedelta(days=6)
                tasks_in_week = Task.objects.filter(buffered_date__range=[week_start - timedelta(days=self.user.user_profile.safety_buffer_days), week_end - timedelta(days=self.user.user_profile.safety_buffer_days)], location=self.location).exclude(id=self.id)
                
                if tasks_in_week.exists():
                    # Find the day with tasks from the same location that has the least total hours
                    best_day = None
                    min_total_hours = float('inf')
                    for day in (week_start + timedelta(n) for n in range(7)):
                        day_tasks = tasks_in_week.filter(buffered_date=day - timedelta(days=self.user.user_profile.safety_buffer_days))
                        day_hours = sum(task.completion_hrs for task in day_tasks) + self.completion_hrs + 1.5
                        if day_hours < min_total_hours and day_hours <= 8:
                            min_total_hours = day_hours
                            best_day = day
                    
                    if best_day:
                        next_date = best_day
                        continue

            # If we couldn't pair the task or it's not a lone task, move to the next day
            next_date += timedelta(days=1)
    
        # Check for potential past occurrences that are still in the future or today
        potential_date = next_date
        while potential_date > today:
            potential_date -= timedelta(days=self.frequency)
            if potential_date >= today:
                next_date = potential_date
            else:
                break
        self.due_date = next_date
        # self.buffered_date = next_date - timedelta(days=self.user.user_profile.safety_buffer_days)
        self.save()
        return next_date

    def all_task_occurences(self, year) -> dict[int, list[date]]:
        today = date.today()
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        occurrences = []
        self.next_occurrence()

        if year == today.year:
            next_date = self.due_date
            while next_date <= end_date:
                occurrences.append(next_date)
                next_date += timedelta(days=self.frequency)
        
            prev_date = self.due_date - timedelta(days=self.frequency)
            while prev_date >= start_date:
                occurrences.append(prev_date)
                prev_date -= timedelta(days=self.frequency)

        elif year < today.year:
            next_date = end_date
            while next_date >= start_date:
                if (next_date - self.due_date).days % self.frequency == 0:
                    occurrences.append(next_date)
                next_date -= timedelta(days=1)

        else:  # year > today.year
            next_date = start_date
            while next_date <= end_date:
                if (next_date - self.due_date).days % self.frequency == 0:
                    occurrences.append(next_date)
                next_date += timedelta(days=1)
        occurrences_per_month = {month: [] for month in range(1, 13)}
        for occurrence in occurrences:
            month = occurrence.month
            occurrences_per_month[month].append(occurrence.strftime('%Y-%m-%d'))                
        return occurrences_per_month

    def get_occurrences(self, end_date):
        occurrences = []
        next_date = self.next_occurrence()
        while next_date <= end_date:
            occurrences.append(next_date)
            next_date += timedelta(days=self.frequency)
        return occurrences

    def json(self):
        warning = None
        if self.due_date and self.user.user_profile.safety_buffer_days:
            buffered_date = self.due_date - self.user.user_profile.safety_buffer_days
            if buffered_date - datetime.now().date() < timedelta(days=0):
                warning = "Task is approaching or past the safety buffer!"
        
        return {"name": self.name, 
                "id": self.id,
                "location": self.location.name,
                "milepost": self.location.milepost,
                "time_taken": self.completion_hrs,
                "warning": warning}

    def __str__(self):
        return self.name

class Location(models.Model):
    name = models.CharField(max_length=200, unique=True)
    milepost = models.FloatField()
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='locations')
    def __str__(self):
        return self.name
    def due_next(self, days) ->  dict[date, list[Task]]:
        due_next = {}
        today = date.today()
        end_date = today + timedelta(days=days)
        for task in self.tasks.all().filter(user=self.user):
            occurrences = [occurrence.strftime('%Y-%m-%d') for occurrence in task.get_occurrences(end_date)]            
            for occurrence in occurrences:
                if occurrence not in due_next:
                    due_next[occurrence] = []
                due_next[occurrence].append(task)
        return due_next
    def this_year_tasks(self, year):
        tasks = self.tasks.all()
        if tasks:
            return {task.name: {"occurences":task.all_task_occurences(year), "frequency": task.frequency} for task in tasks}
        else:
            return
    
    def next_task(self):
        tasks = self.tasks.all()
        if tasks: 
            return min(tasks, key=lambda task: task.next_occurrence())
        else: 
            return
    
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance, availability={})

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.user_profile.save()