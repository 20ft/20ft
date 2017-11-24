from _thread import allocate_lock
term_lock = allocate_lock()
term_lock.acquire()


def tf_main(location, environment, portmap, preboot, volumes, cmd, args):
    def terminate(container):
        term_lock.release()

    location.best_node().spawn_container("tfnz/ends_test", termination_callback=terminate)
    term_lock.acquire()
