class PistonDispenser:
    """
    PistonDispenser is a class representing the piston dispensers on the side of the Jubilee.
    It is used to keep track of the number of pistons in each dispenser.
    """
    index : int      # index of the dispenser on the side of the Jubilee
    num_pistons: int # number of pistons in the dispenser
    x: float         # x coordinate of the dispenser
    y: float         # y coordinate of the dispenser

    def __init__(self, index, num_pistons):
        self.index = index
        self.num_pistons = num_pistons

    def remove_piston(self):
        if self.num_pistons > 0:
            self.num_pistons -= 1
        else:
            raise ValueError("No pistons in dispenser")
