import time
import threading

class TrafficLogic:
    """
    Manages the state of the traffic light system in a separate thread.
    
    NEW LOGIC:
    1. Implements a fixed-order, round-robin cycle (1->2->3->4).
    2. Green time is dynamic based on density (T_green = T_min + density).
    3. Includes a 3-second orange light phase.
    4. Minimum green time (T_min) is 5 seconds.
    5. Handles ambulance overrides based on lane priority (1 > 2 > 3 > 4).
    6. Calculates dynamic time for the first lane on startup.
    """
    
    def __init__(self):
        # Initialize state for 4 lanes
        self.lanes = {
            1: {'density': 0, 'ambulance': False, 'status': 'red'},
            2: {'density': 0, 'ambulance': False, 'status': 'red'},
            3: {'density': 0, 'ambulance': False, 'status': 'red'},
            4: {'density': 0, 'ambulance': False, 'status': 'red'}
        }
        
        # --- Timers and Configuration (Updated) ---
        self.timer = 0
        self.base_green_time = 5      # T_min: Minimum green light time (Set to 5s)
        self.orange_light_duration = 3 # New: Orange light phase duration
        self.max_extra_time = 15      # Max extra time for high density
        
        self.ambulance_override = False
        self.lock = threading.Lock() 

        # --- Corrected Fixed Cycle Logic ---
        self.priority_order = [1, 2, 3, 4]
        self.current_priority_index = 0 
        self.current_active_lane = self.priority_order[self.current_priority_index] # Lane 1
        
        # Set the starting lane to green
        self.lanes[self.current_active_lane]['status'] = 'green'
        
        # Set a default duration. This will be immediately recalculated on the first run.
        self.current_green_duration = self.base_green_time 
        
        # --- Corrected Startup Logic ---
        self.is_first_run = True # Flag to force immediate density check on start
        
        # Start the logic loop in a background thread
        self.logic_thread = threading.Thread(target=self._run_logic, daemon=True)
        self.logic_thread.start()

    def update_lane_data(self, lane_id, density, ambulance):
        """Called by the Flask video processor to update real-time data."""
        with self.lock:
            self.lanes[lane_id]['density'] = density
            self.lanes[lane_id]['ambulance'] = ambulance

    def get_system_state(self):
        """Called by the Flask API to send the current state to the frontend."""
        with self.lock:
            # Return a copy to avoid modification issues
            return self.lanes.copy()

    def _run_logic(self):
        """
        The main logic loop with corrected startup, ambulance, and orange light logic.
        """
        while True:
            time.sleep(1) # Logic ticks every 1 second
            
            with self.lock:
                
                # --- 1. Corrected Startup Logic ---
                if self.is_first_run:
                    # On the very first tick, immediately calculate the *correct*
                    # green time for the starting lane (Lane 1) based on its density.
                    print("System startup: Calculating initial green time for Lane 1.")
                    self._set_green_light(self.current_active_lane) 
                    self.is_first_run = False
                    self.timer = 0 # Start the timer fresh
                    continue

                # --- 2. Corrected Ambulance Override Logic ---
                # Find all lanes with ambulances
                ambulance_lanes_detected = [i for i in range(1, 5) if self.lanes[i]['ambulance']]
                
                if ambulance_lanes_detected:
                    # Find the highest priority ambulance lane (1 > 2 > 3 > 4)
                    priority_ambulance_lane = None
                    for lane_id in self.priority_order: # Check in order [1, 2, 3, 4]
                        if lane_id in ambulance_lanes_detected:
                            priority_ambulance_lane = lane_id
                            break # Found the highest priority one

                    if not self.ambulance_override:
                        print(f"AMBULANCE DETECTED! Priority to Lane {priority_ambulance_lane}.")
                    self.ambulance_override = True
                    
                    # If the priority lane is already green, just keep it green
                    if self.lanes[priority_ambulance_lane]['status'] == 'green':
                        self.timer = 0 # Reset timer to keep it green
                    else:
                        # If another lane is active (green or orange), force it red
                        if self.lanes[self.current_active_lane]['status'] != 'red':
                            print(f"Ambulance override: Forcing Lane {self.current_active_lane} to Red.")
                            self.lanes[self.current_active_lane]['status'] = 'red'
                        
                        # Immediately set the ambulance lane to green
                        self._set_green_light(priority_ambulance_lane, is_ambulance=True)
                    
                    continue # Skip normal logic
                
                # Reset cycle after ambulance has cleared
                if self.ambulance_override and not ambulance_lanes_detected:
                    print("Ambulance clear. Resetting cycle to start from Lane 1.")
                    self.ambulance_override = False
                    self.lanes[self.current_active_lane]['status'] = 'red' # Set current lane red
                    self.current_priority_index = -1 # Will increment to 0
                    self.timer = self.orange_light_duration # Force immediate switch on next relevant tick
                
                # --- 3. CORRECTED FIXED-CYCLE (Green -> Orange -> Red) ---
                self.timer += 1
                
                current_status = self.lanes[self.current_active_lane]['status']

                # A. Check if GREEN light time is up
                if current_status == 'green' and self.timer >= self.current_green_duration:
                    # Switch to ORANGE
                    self._set_orange_light(self.current_active_lane)
                
                # B. Check if ORANGE light time is up
                elif current_status == 'orange' and self.timer >= self.orange_light_duration:
                    # Switch to RED and find the next GREEN lane
                    
                    # 1. Set current lane to red
                    self.lanes[self.current_active_lane]['status'] = 'red'
                    
                    # 2. Get the next lane from the fixed priority list
                    self.current_priority_index = (self.current_priority_index + 1) % len(self.priority_order)
                    
                    if self.current_priority_index == 0:
                        print("\n--- Full cycle complete. Restarting from Lane 1. ---")

                    # 3. Get the new lane ID
                    next_lane = self.priority_order[self.current_priority_index]
                        
                    # 4. Set the new lane to green
                    print(f"Switching light: Lane {self.current_active_lane} (Red) -> Next Lane {next_lane} (Green)")
                    self._set_green_light(next_lane)
    
    def _set_orange_light(self, lane_id):
        """Helper function to set a lane to orange."""
        self.lanes[lane_id]['status'] = 'orange'
        self.timer = 0 # Reset timer for the orange phase
        print(f"Lane {lane_id} is now Orange for {self.orange_light_duration}s")

    def _set_green_light(self, lane_id, is_ambulance=False):
        """
        Helper function to set a lane to green and others to red.
        Calculates the new green light duration based on density.
        """
        for i in range(1, 5):
            if i != lane_id:
                self.lanes[i]['status'] = 'red'
        
        self.lanes[lane_id]['status'] = 'green'
        self.current_active_lane = lane_id # Update the active lane
        
        if is_ambulance:
            # Give a fixed, long green light for ambulances
            self.current_green_duration = self.base_green_time + self.max_extra_time
        else:
            # Calculate dynamic green time: T_green = T_min + (k * D)
            # (k=1 second per vehicle, capped at max_extra_time)
            density = self.lanes[lane_id]['density']
            extra_time = min(density, self.max_extra_time)
            self.current_green_duration = self.base_green_time + extra_time
        
        self.timer = 0 # Reset timer for the new green light
        
        print(f"Lane {lane_id} is Green for {self.current_green_duration}s (Density: {self.lanes[lane_id]['density']})")