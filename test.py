import ping3
import time


IP_ADDRESS = "8.8.8.8"



def time_str(start, end):
    return str(round((end - start) * 1000)) + " ms"


ping3.EXCEPTIONS = True
# ping3.DEBUG = True

def test():
    # sanity check first
    ping3.ping(IP_ADDRESS)

    for i in range(1, 30):
        try:
            start = time.time()
            res = ping3.ping(IP_ADDRESS, ttl=i, seq=i, unit="ms")
            print("[{}]\t{} ms\t{}".format(i, round(res), IP_ADDRESS))
            break
        except ping3.errors.TimeToLiveExpired as e:
            end = time.time()
            print("[{}]\t{}\t{}".format(i, time_str(start, end), e.ip_header["src_addr"]))
        except ping3.errors.Timeout as e:
            print("[{}]\tTimeout".format(i))
        except ping3.errors.PingError as e:
            print("[{}]\tPingError".format(i))


def test2():
    try:
        res = ping3.ping(
            "quake.com",
            src_addr="",
            unit="ms",
            ttl=5
        )
    except ping3.errors.Timeout:
        print("Timeout")
    except ping3.errors.TimeToLiveExpired as e:
        print("TTL Expired", e.ip_header["src_addr"])


if __name__ == "__main__":
    test()
    # test2()
