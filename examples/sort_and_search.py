def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    mid = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + mid + quicksort(right)


def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        m = (lo + hi) // 2
        if arr[m] == target:
            return m
        if arr[m] < target:
            lo = m + 1
        else:
            hi = m - 1
    return -1


if __name__ == "__main__":
    print(quicksort([3, 1, 2]))
