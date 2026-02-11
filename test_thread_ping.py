import ping3
import threading


DESTINATION = "bad.horse"
HOPS = 50

ping3.EXCEPTIONS = True


def ping_threaded(ttl: int, response):
    try:
        ms = ping3.ping(DESTINATION, ttl=ttl, unit="ms")
        msg = "[{}] Ping to {}: {} ms".format(ttl, DESTINATION, ms)
    except ping3.errors.TimeToLiveExpired as e:
        msg = "[{}] Ping to {}: TTL Expired {}".format(ttl, DESTINATION, e.ip_header["src_addr"])
    except ping3.errors.PingError as e:
        msg = "[{}] Ping to {}: {}".format(ttl, DESTINATION, e)
    except:
        msg = "[{}]".format(ttl)

    response.append(msg)


def main():
    threads = []
    for ttl in range(1, HOPS):
        # Obviously not best practice
        return_msg = []
        t = threading.Thread(target=ping_threaded, args=[ttl, return_msg])
        t.start()
        threads.append((t, return_msg))
    
    for t, return_msg in threads:
        t: threading.Thread
        t.join()
        print(return_msg[0])


if __name__ == "__main__":
    main()
