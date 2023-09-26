from .models import Route

def routes_data(request):
    # Fetch the list of routes
    routes = Route.objects.all()

    context = {
        'routes': routes,
    }
      
    return context
