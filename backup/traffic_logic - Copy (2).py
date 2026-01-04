import time
import threading

class TrafficLogic:
    """
    Manages the state of the traffic light system in a separate thread.
    
    CORRECTED LOGIC:
    1. Implements a fixed-order, round-robin cycle (1->2->3->4).
    2. Green time is dynamic based on density (T_green = T_min + density).
    3. Includes a 3-second orange light phase.
    4. Minimum green time (T_min) is 5 seconds.
    5. Correctly handles ambulance override and resumes the cycle afterward.
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
        
        # --- Timers and Configuration ---
        self.timer = 0
        self.base_green_time = 5      # T_min: Minimum green light time
        self.orange_light_duration = 3 # Orange light phase duration
        self.max_extra_time = 15      # Max extra time for high density
        
        self.ambulance_override = False
        self.lock = threading.Lock() 

        # --- Fixed Cycle Logic ---
        self.priority_order = [1, 2, 3, 4]
        self.current_priority_index = 0 
        self.current_active_lane = self.priority_order[self.current_priority_index] # Lane 1
        
        self.lanes[self.current_active_lane]['status'] = 'green'
        self.current_green_duration = self.base_green_time 
        
        self.is_first_run = True # Flag to force immediate density check on start
        
        self.logic_thread = threading.Thread(target=self._run_logic, daemon=True)
        self.logic_thread.start()

    def update_lane_data(self, lane_id, density, ambulance):
        """Called by the Flask video processor to update real-time data."""
        with self.lock:
            # Only update density if the light is green
            if self.lanes[lane_id]['status'] == 'green':
                 self.lanes[lane_id]['density'] = density
            self.lanes[lane_id]['ambulance'] = ambulance

    def get_system_state(self):
        """
        Called by the Flask API.
        Returns the full lane state + a timer object for the countdown.
        """
        with self.lock:
            state_copy = self.lanes.copy()
            
            time_remaining = 0
            # Check for the active lane, as it's the only one with a timer
            if self.current_active_lane in state_copy:
                active_status = state_copy[self.current_active_lane]['status']
                
                if active_status == 'green':
                    time_remaining = self.current_green_duration - self.timer
                elif active_status == 'orange':
                    time_remaining = self.orange_light_duration - self.timer
                
                # Add time_remaining to the state for the active lane
                state_copy[self.current_active_lane]['time_remaining'] = max(0, time_remaining)

            return state_copy


    def _run_logic(self):
        """
        The main logic loop with corrected startup, ambulance, and orange light logic.
        """
        while True:
            time.sleep(1) # Logic ticks every 1 second
            
            with self.lock:
                
                # --- 1. Corrected Startup Logic ---
                if self.is_first_run:
                    print("System startup: Calculating initial green time for Lane 1.")
                    self._set_green_light(self.current_active_lane) 
                    self.is_first_run = False
                    self.timer = 0
                    continue

                # --- 2. Corrected Ambulance Override Logic ---
                ambulance_lanes_detected = [i for i in range(1, 5) if self.lanes[i]['ambulance']]
                
                if ambulance_lanes_detected:
                    priority_ambulance_lane = None
                    for lane_id in self.priority_order: # Check in order [1, 2, 3, 4]
                        if lane_id in ambulance_lanes_detected:
                            priority_ambulance_lane = lane_id
                            break 

                    if not self.ambulance_override:
                        print(f"AMBULANCE DETECTED! Priority to Lane {priority_ambulance_lane}.")
                    self.ambulance_override = True
                    
                    if self.lanes[priority_ambulance_lane]['status'] == 'green':
                        self.timer = 0 # Keep it green
                    else:
                        if self.lanes[self.current_active_lane]['status'] != 'red':
                            print(f"Ambulance override: Forcing Lane {self.current_active_lane} to Red.")
                            self.lanes[self.current_active_lane]['status'] = 'red'
                        
                        self._set_green_light(priority_ambulance_lane, is_ambulance=True)
                    
                    continue 
                
                # --- 3. Corrected Ambulance Reset Logic ---
                # This block now correctly transitions from override back to the normal cycle
                if self.ambulance_override and not ambulance_lanes_detected:
                    print("Ambulance clear. Resuming normal cycle.")
                    self.ambulance_override = False
                    
                    # If the ambulance lane is currently green, switch it to orange
                    # and let the normal cycle take over from there.
                    if self.lanes[self.current_active_lane]['status'] == 'green':
                        print(f"Finishing ambulance cycle for Lane {self.current_active_lane}.")
                        self._set_orange_light(self.current_active_lane)
                        # Don't 'continue'. Let the timer increment normally from here.
                
                # --- 4. NORMAL FIXED-CYCLE (Green -> Orange -> Red) ---
                self.timer += 1
                
                current_status = self.lanes[self.current_active_lane]['status']

                # A. Check if GREEN light time is up
                if current_status == 'green' and self.timer >= self.current_green_duration:
                    self._set_orange_light(self.current_active_lane)
                
                # B. Check if ORANGE light time is up
                elif current_status == 'orange' and self.timer >= self.orange_light_duration:
                    self.lanes[self.current_active_lane]['status'] = 'red'
                    
                    self.current_priority_index = (self.current_priority_index + 1) % len(self.priority_order)
                    
                    if self.current_priority_index == 0:
                        print("\n--- Full cycle complete. Restarting from Lane 1. ---")

                    next_lane = self.priority_order[self.current_priority_index]
                        
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
        Calculates the new green light duration.
        """
        for i in range(1, 5):
            if i != lane_id:
                self.lanes[i]['status'] = 'red'
        
        self.lanes[lane_id]['status'] = 'green'
        self.current_active_lane = lane_id
        
        if is_ambulance:
            self.current_green_duration = self.base_green_time + self.max_extra_time
        else:
            density = self.lanes[lane_id]['density']
            extra_time = min(density, self.max_extra_time)
            self.current_green_duration = self.base_green_time + extra_time
        
        self.timer = 0 
        
        print(f"Lane {lane_id} is Green for {self.current_green_duration}s (Density: {self.lanes[lane_id]['density']})")