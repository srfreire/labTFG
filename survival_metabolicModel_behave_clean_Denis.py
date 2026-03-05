import random
import tkinter as tk
import time

# CLASS: ORGANISM. The organism that moves around the map to find food sources
# The organism has two main survival factors: energy and nutrients
# The organism also has three main actions: move, gather, and rest


class Organism:
    def __init__(self, x, y, perception_range, threshold_hungry):
        self.x = x
        self.y = y
        self.nutrients = 25
        self.energy = 20
        self.nutrientsState = 'Fine'
        self.energyState = 'Fine'
        self.age = 0
        self.perception_range = perception_range
        self.threshold_hungry = threshold_hungry    
        self.accessible_food_sources = []
        self.nutrientsHistory = []
        self.energyHistory = []
        self.nutrientsStateHistory = []
        self.energyStateHistory = []
        self.actionHistory = []
        self.nutrientsHistory.append(self.nutrients)
        self.energyHistory.append(self.energy)
        self.nutrientsStateHistory.append(self.nutrientsState)
        self.energyStateHistory.append(self.energyState)
        self.SurvivalState = 'Alive'

    # ACTION: REST. Resting does not change position
    def rest(self):
        # Resting does not change position
        print("I am resting")
        self.action = 'Rest'
        self.actionHistory.append(self.action)
        self.updateState(self.action)
        
    # ACTION: PERCEIVE. Perceiving updates the accessible food sources
    def perceive(self, food_sources):
        print("I am perceiving")
        self.action = 'Perceive'
        self.actionHistory.append(self.action)
        print(food_sources)
        for food in food_sources:
            print(food)
            distance_food = abs(food[0] - self.x) + abs(food[1] - self.y)
            print(distance_food)
            if distance_food <= self.perception_range:
                if food not in self.accessible_food_sources:
                    self.accessible_food_sources.append(food)
                    print(self.accessible_food_sources)
        self.updateState(self.action)
            
    # ACTION: MOVE. Moving does change the position of the organism 
    def move(self):
        print("I am moving")
        self.action = 'Move'
        self.actionHistory.append(self.action)
        if self.accessible_food_sources:
            closest_food = min(self.accessible_food_sources, key=lambda f: abs(f[0] - self.x) + abs(f[1] - self.y))
            print(closest_food)
            if closest_food[0] > self.x:
                self.x += 1
            elif closest_food[0] < self.x:
                self.x -= 1
            if closest_food[1] > self.y:
                self.y += 1
            elif closest_food[1] < self.y:
                self.y -= 1
        else:
            self.x += random.choice([-1, 1])
            self.y += random.choice([-1, 1])
        self.updateState(self.action)        

    # ACTION: EAT. Eating involves eating an accessible food source
    def eat(self):
        print("I am eating")
        self.action = 'Eat'
        self.actionHistory.append(self.action)
        self.updateState(self.action)

    # ACTION: GATHER. Gathering involves moving to the closest food source and eating it
    def gather(self, food_sources):
        print("I am gathering")
        self.action = 'Gather'
        self.actionHistory.append(self.action)
        self.perceive(food_sources)
        self.move()
        for food in self.accessible_food_sources:
            if (self.x, self.y) == (food[0], food[1]):
                self.eat()
                self.accessible_food_sources.remove(food)   
       
    # UPDATE STATE: Updates the state of the organism based on the action taken
    def updateState(self, action):
        if action == 'Rest':
            self.energy += 1
            self.nutrients -= 1
            self.energyHistory.append(self.energy)
            self.nutrientsHistory.append(self.nutrients)
        elif action == 'Perceive':
            self.energy -= 1
            self.nutrients -= 1
            self.energyHistory.append(self.energy)
            self.nutrientsHistory.append(self.nutrients)
        elif action == 'Move':
            self.energy -= 1
            self.nutrients -= 1
            self.age += 1
            self.energyHistory.append(self.energy)
            self.nutrientsHistory.append(self.nutrients)
        elif action == 'Eat':
            self.energy += 1
            self.nutrients += 10
            self.energyHistory.append(self.energy)
            self.nutrientsHistory.append(self.nutrients)


        if self.energy >= 15:
            self.energyState = 'Fine'
            self.energyStateHistory.append(self.energyState)
        elif self.energy > 1:
            self.energyState = 'Tired'
            self.energyStateHistory.append(self.energyState)
        else:
            self.energyState = 'Exhausted'
            self.energyStateHistory.append(self.energyState)

        if self.nutrients >= 20:   
            self.nutrientsState = 'Fine'
            self.nutrientsStateHistory.append(self.nutrientsState)
        elif self.nutrients >= self.threshold_hungry:
            self.nutrientsState = 'Ok'
            self.nutrientsStateHistory.append(self.nutrientsState)
        elif self.nutrients >= 1:
            self.nutrientsState = 'Hungry'
            self.nutrientsStateHistory.append(self.nutrientsState)
        else:
            self.SurvivalState = 'Dead'

    # RECALL STATE: Recalls the current state of the organism
    def recallState(self):
        current_energyState = self.energyState
        current_nutrientsState = self.nutrientsState

        return current_energyState, current_nutrientsState

    # MOTIVATE: Motivates the organism to move from its current state to a desired state
    def motivate(self, current_energyState, current_nutrientsState):
        if current_energyState == 'Fine' and current_nutrientsState == 'Fine':
            print("I am Fine/Fine. I want to keep fine")
            desired_energyState = 'Fine'
            desired_nutrientsState = 'Fine'
        elif current_energyState == 'Fine' and current_nutrientsState == 'Ok':
            print("I am Fine and my Nutrients are Ok. I want to keep fine and Ok")
            desired_energyState = 'Fine'
            desired_nutrientsState = 'Ok'
        elif current_energyState == 'Fine' and current_nutrientsState == 'Hungry':
            print("I am Hungry. I want to be Ok")
            desired_energyState = 'Fine'
            desired_nutrientsState = 'Ok'
        elif current_energyState == 'Tired' and current_nutrientsState == 'Fine':
            print("I am Tired but my nutrients are Fine. I want to be Fine")
            desired_energyState = 'Fine'
            desired_nutrientsState = 'Fine'
        elif current_energyState == 'Tired' and current_nutrientsState == 'Ok':
            print("I am Tired and my nutrients are Ok. I want to be Fine and Ok")
            desired_energyState = 'Fine'
            desired_nutrientsState = 'Ok'
        elif current_energyState == 'Tired' and current_nutrientsState == 'Hungry':
            print("I am Tired and Hungry. I want to be Tired but Ok")
            desired_energyState = 'Tired'
            desired_nutrientsState = 'Ok'
        elif current_energyState == 'Exhausted':
            print("I am Exhausted. I want to be Tired")
            desired_energyState = 'Tired'
            desired_nutrientsState = 'Ok'

        return desired_energyState, desired_nutrientsState

    # DECIDE: Decides the action to take given the current and desired states
    def decide(self, current_energyState, current_nutrientsState, desired_energyState, desired_nutrientsState):

        if current_energyState == 'Fine' and current_nutrientsState == 'Fine':
            action = 'Rest'
        elif current_energyState == 'Fine' and current_nutrientsState == 'Ok':
            action = 'Rest'
        elif current_energyState == 'Fine' and current_nutrientsState == 'Hungry':
            # Check if there are enough resources to Gather
            if self.energy >= 2 and self.nutrients >= 3:
                action = 'Gather'
            else:
                action = 'Rest'
        elif current_energyState == 'Tired' and current_nutrientsState == 'Fine':
            action = 'Rest'
        elif current_energyState == 'Tired' and current_nutrientsState == 'Ok':
            action = 'Rest'
        elif current_energyState == 'Tired' and current_nutrientsState == 'Hungry':
            # Check if there are enough resources to Gather
            if self.energy >= 2 and self.nutrients >= 3:
                action = 'Gather'
            else:
                action = 'Rest'
        elif current_energyState == 'Exhausted':
            action = 'Rest'

        return action

    # RUN ACTION: Runs the action based on the given input
    def runAction(self, action, food_sources):

        if action == 'Rest':
            print("I am Resting")
            self.rest()
        elif action == 'Gather':
            print("I am Gathering")
            self.gather(food_sources)

    # BEHAVE: Simulates the agent's behavior
    def behave(self, food_sources):  

        # 1. Recall State
        current_energyState, current_nutrientsState = self.recallState()
        print("current_energyState:", current_energyState)
        print("current_nutrientsState:", current_nutrientsState)

        # 2. Motivate
        desired_energyState, desired_nutrientsState = self.motivate(current_energyState, current_nutrientsState)
        print("desired_energyState:", desired_energyState)
        print("desired_nutrientsState:", desired_nutrientsState)

        # 3. Decide
        current_action = self.decide(current_energyState, current_nutrientsState, desired_energyState, desired_nutrientsState)
        print("current_action:", current_action)

        # 4. Run Action
        self.runAction(current_action, food_sources)


  # CLASS: GRIDMAP. The map where the simulation takes place
  # The map is composed by squares called cells
  # Each cell has a position in the map
  # Each cell can be empty or can contain an organism

class GridMap:
    def __init__(self, master, width, height, grid_size=50):
        self.master = master
        self.master.title('Organism Survival Simulation')
        self.grid_size = grid_size
       
        # Create canvas
        self.width = width * grid_size
        self.height = height * grid_size
        self.canvas = tk.Canvas(master, width=self.width, height=self.height, bg='white')
        self.canvas.pack()
       
        # Draw grid
        self.draw_grid()

    def draw_grid(self):
        # Draw vertical lines
        for x in range(0, self.width, self.grid_size):
            self.canvas.create_line(x, 0, x, self.height, fill='gray', dash=(2, 2))
       
        # Draw horizontal lines
        for y in range(0, self.height, self.grid_size):
            self.canvas.create_line(0, y, self.width, y, fill='gray', dash=(2, 2))

    def clear_canvas(self):
        # Clear everything except grid lines
        for item in self.canvas.find_all():
            if self.canvas.type(item) != "line":  # Don't remove grid lines
                self.canvas.delete(item)

    def place_shape(self, grid_x, grid_y, shape_type, color):
        x = grid_x * self.grid_size + self.grid_size // 2
        y = grid_y * self.grid_size + self.grid_size // 2
        size = self.grid_size * 0.8
       
        if shape_type == 'circle':
            radius = size // 2
            self.canvas.create_oval(x - radius, y - radius,
                                  x + radius, y + radius,
                                  fill=color)
        elif shape_type == 'square':
            half_size = size // 2
            self.canvas.create_rectangle(x - half_size, y - half_size,
                                       x + half_size, y + half_size,
                                       fill=color)


# CLASS: ENVIRONMENT
# The environment is composed by a grid of cells
# Each cell can be empty or can contain food
# Each cell can be empty or can contain an organism
# The environment provides a plot function to visualize the dynamics of the organisms
class Environment:
    def __init__(self, width, height, food_count):
        self.width = width
        self.height = height
        self.organisms = []
        self.food_sources = [(random.randint(0, width-1), random.randint(0, height-1)) for _ in range(food_count)]
       
        # Initialize Tkinter window
        self.root = tk.Tk()
        self.grid_map = GridMap(self.root, width, height)

    def add_organism(self, organism):
        self.organisms.append(organism)

    def update(self):
        for organism in self.organisms:
            if organism.SurvivalState == 'Alive':
                organism.behave(self.food_sources)
                if (organism.x, organism.y) in self.food_sources:
                    # organism.eat()
                    self.food_sources.remove((organism.x, organism.y))
                    self.food_sources.append((random.randint(0, self.width-1), random.randint(0, self.height-1)))
        self.visualize()
        self.root.update()

    def visualize(self):
        self.grid_map.clear_canvas()
        self.grid_map.draw_grid()
       
        # Draw food sources as orange squares
        for food_x, food_y in self.food_sources:
            self.grid_map.place_shape(food_x, food_y, 'square', 'orange')
       
        # Draw organisms as circles with colors depending on energy level
        for organism in self.organisms:
            if organism.SurvivalState == 'Alive':
                if 0 <= organism.x < self.width and 0 <= organism.y < self.height:
                    if organism.nutrients < 100 and organism.nutrients >= 20:
                        self.grid_map.place_shape(organism.x, organism.y, 'circle', 'green')
                    elif organism.nutrients < 20 and organism.nutrients >= organism.threshold_hungry:
                        self.grid_map.place_shape(organism.x, organism.y, 'circle', 'yellow')
                    elif organism.nutrients < threshold_hungry:
                        self.grid_map.place_shape(organism.x, organism.y, 'circle', 'red')


    # Make a number of plots: energy, nutrients, energyState, nutrientsState and action
    def plot(self, organism):
        import matplotlib.pyplot as plt
        import numpy as np

        plt.figure(figsize=(20, 10))
        plt.subplot(2, 3, 1)
        plt.title("Energy")
        plt.plot(organism.energyHistory)
        plt.subplot(2, 3, 4)
        plt.title("Nutrients")
        plt.plot(organism.nutrientsHistory)
        plt.subplot(2, 3, 2)
        plt.title("Energy State")
        plt.plot(organism.energyStateHistory)
        plt.subplot(2, 3, 5)
        plt.title("Nutrients State")
        plt.plot(organism.nutrientsStateHistory)
        plt.subplot(2, 3, 3)
        plt.title("Action")
        plt.plot(organism.actionHistory)
        plt.show()

        
     
# MAIN PROGRAM: Where the simulation takes place

# Initialize organisms
organisms_count = 1
food_count = 5
perception_range = 2
threshold_hungry = 15

# Initialize environment and add organisms on it
env = Environment(10, 10, food_count)
for _ in range(organisms_count):
    env.add_organism(Organism(random.randint(3, 6), random.randint(3, 6), perception_range, threshold_hungry))
    perception_range -= 5

# Start the simulation
for _ in range(100):
    print(f"Organisms: {len(env.organisms)}")
    for i, org in enumerate(env.organisms):
        print(f"Organism {i+1}: Energy={org.energy}, Energy State={org.energyState}, Nutrients={org.nutrients}, Nutrients State={org.nutrientsState}")
    env.update()
    time.sleep(0.5)


# Show all plots for all organisms  (energy, nutrients, energyState, nutrientsState and action)
for organism in env.organisms:
    env.plot(organism)
 
for organism in env.organisms:
    print(organism.energyStateHistory)

    