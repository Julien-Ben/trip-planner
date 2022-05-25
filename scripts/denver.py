from graph import Station, Timetable, Path, Marks, Solutions, RouteStop, WalkingStop
from typing import List


class Denver:
    def __init__(self, g_dep_time: int, threshold: float, g_start: Station, g_end: Station,
                 timetable: Timetable, n_sols_expected: int, target_arr_time: int):
        #self.graph = graph
        self.g_dep_time = g_dep_time
        self.threshold = threshold
        self.g_start = g_start
        self.g_end = g_end
        self.timetable = timetable
        self.n_sols_expected = n_sols_expected
        self.target_arr_time = target_arr_time
        self.TRANSFER_TIME = 120  # 2 minutes
        self.FIRST_STATION_TS = 0  # chosen timestamp of the first station in graph (and last in real world)

    # prefix g_ is for reversed graph, prefix i_ is for input values
    def denver(self, n_sols_found: int = 0, blacklisted_route: str = "", stop_recursion: bool = False) -> List[Path]:
        marks = Marks(blacklisted_route)
        solutions = Solutions(self.g_dep_time, self.g_end)
        self.init_first_station(self.g_start, marks, self.timetable)
        while not marks.empty():
            # NOTE: pour les 3 fonctions, passage par référence assumed des marks (et donc du graph)
            self.update_lines(marks, solutions)
            self.update_walks(marks)
            self.update_stations(marks, solutions, self.timetable)

        solutions.sort_solutions()
        n_sols_found += solutions.n_solutions()
        if not stop_recursion and n_sols_found < self.n_sols_expected and solutions.n_solutions():
            for route_removed in solutions.sols[0].route_names:  # solutions sorted by best first
                # Run the same algorithms on a graph with one route from the solution removed
                solutions.sols += self.denver(n_sols_found, route_removed, stop_recursion=True)

        return solutions.sols

    def init_first_station(self, g_start: Station, marks: Marks, timetable: Timetable) -> None:
        g_start.update_arrival(self.FIRST_STATION_TS, None, 1)
        #marks.mark_station(g_start)  # TODO: verify
        for stop in g_start.stops:
            if isinstance(stop, RouteStop):
                dep_time, _ = timetable.previous_arrival(stop, self.FIRST_STATION_TS)
                stop.update_arrival(dep_time, g_start, 1)
                marks.mark_route(stop)
            elif isinstance(stop, WalkingStop):
                stop.update_arrival(self.FIRST_STATION_TS, g_start, 1)
                marks.mark_walk(stop)

    def update_lines(self, marks: Marks, solutions: Solutions) -> None:
        # The stop associated with each route is the first stop with a new arr_time on this route
        for route_name, stop in marks.route_marks.items():
            update_prev = True
            while update_prev and stop.prev_stop is not None:
                new_arr_time = stop.arr_time + stop.travel_time
                # Local & target pruning
                if new_arr_time < solutions.best_target_arr_time and new_arr_time < stop.prev_stop.arr_time:
                    # Update the next stop
                    stop.prev_stop.update_arrival(new_arr_time, stop, stop.acc_success)  # update next stop
                    marks.mark_station(stop.prev_stop.station)  # mark next stop's station
                    stop = stop.prev_stop
                else:
                    update_prev = False
        marks.flush_routes()  # unmark all routes

    def update_walks(self, marks: Marks) -> None:
        """Update WalkingStop's neighbors until it converges"""
        while not marks.walk_empty():
            stop = marks.pop_walk()
            for neighbor, walk_time in stop.neighbors:
                new_arr_time = stop.arr_time + walk_time
                if neighbor.arr_time > new_arr_time:
                    neighbor.update_arrival(new_arr_time, stop, stop.acc_success)
                    marks.mark_walk(neighbor)
                    marks.mark_station(neighbor.station)

    def update_stations(self, marks: Marks, solutions: Solutions, timetable: Timetable) -> None:
        for station in marks.station_marks:
            earliest_stop = station.get_earliest_stop()  # get the stop with has the earliest arrival time
            new_arr_time = earliest_stop.arr_time + self.TRANSFER_TIME

            # We update the station and station's stops if:
            # - the new earliest arrival time is different from the current one 
            #   (if it's different then it's always better than the previous one, o.w. it wouldn't have changed)
            # - the previous node is not the same as new earliest stop
            # - the accumulated journey success probability is different
            if station.arr_time != new_arr_time or station.previous_node != earliest_stop \
                    or station.acc_success != earliest_stop.acc_success:

                station.update_arrival(new_arr_time, earliest_stop, earliest_stop.acc_success)
                # For each of the station's stop, see if the new earliest trip improves its arr_time
                rw_station_arr_time = timetable.target_arr_time - station.arr_time
                for stop in station.stops:
                    #TODO if stop != earliest_stop
                    if isinstance(stop, RouteStop):
                        # Note : All calls to timetable functions must take real-world arguments. Stored returned values
                        # are named relative to the graph and not the real world. Our graph takes real-world target
                        # arrival time as it's departure time, and adds travel time to it instead of subtracting,
                        # so here we need to convert back to real-world time. rw_ stands for real_world
                        rw_previous_arrival_time, idx = timetable.previous_arrival(stop, rw_station_arr_time)
                        if idx == -1:  # no previous departure was found
                            continue
                        wait_time = rw_station_arr_time - rw_previous_arrival_time
                        new_acc_success, safe = timetable.assert_safe_transfer(stop, idx, wait_time, self.threshold,
                                                                               stop.acc_success)
                        # check previous arrival times until we find that is safe enough or checked all of them
                        idx -= 1
                        while not safe and station.arr_time + wait_time < stop.arr_time and idx >= 0:
                            rw_previous_arrival_time = timetable.get_stop_arrival_time(stop, idx)
                            wait_time = rw_station_arr_time - rw_previous_arrival_time
                            new_acc_success, safe = timetable.assert_safe_transfer(stop, idx, wait_time)
                            idx -= 1

                        if safe and station.arr_time + wait_time < stop.arr_time and wait_time > 0:
                            stop.update_arrival(station.arr_time + wait_time, station, new_acc_success)
                            marks.mark_route(stop)
                    elif isinstance(stop, WalkingStop):
                        if station.arr_time < stop.arr_time:
                            stop.update_arrival(station.arr_time, station, station.acc_success)
                            marks.mark_walk(stop)

                    # Save all paths leading to the target_station
                    if station == solutions.target_station:
                        solutions.save(Path.make(station, stop, self.target_arr_time))

        marks.flush_stations()