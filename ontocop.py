import argparse
import functools
import typing

import lxml.etree as etree
import owlready2
import rdflib
import rdflib.namespace
import rdflib.plugins.sparql
import requests


def check_consistency(ontology: rdflib.Graph) -> list[str]:
    """Check if an OWL ontology is internally consistent."""
    print("Checking ontology consistency...")
    world = owlready2.World()
    graph = world.as_rdflib_graph()
    with world.get_ontology("http://localhost/"):
        graph += ontology
    try:
        owlready2.sync_reasoner_pellet(world, debug=0)
    except owlready2.OwlReadyInconsistentOntologyError:
        return ["The ontology is inconsistent"]
    inconsistent_classes = ", ".join(c.__name__ for c in world.inconsistent_classes())
    if inconsistent_classes:
        return [
            f"There are inconsistent classes in the "
            f"ontology: {inconsistent_classes}"
        ]
    return []


class _OOPS(rdflib.namespace.DefinedNamespace):

    pitfall: rdflib.URIRef
    warning: rdflib.URIRef
    suggestion: rdflib.URIRef
    hasImportanceLevel: rdflib.URIRef

    _NS = rdflib.namespace.Namespace("http://oops.linkeddata.es/def#")


def _oops_request_body(ontology: rdflib.Graph) -> bytes:
    root = etree.Element("OOPSRequest")
    root.append(etree.Element("OntologyURI"))
    content = etree.Element("OntologyContent")
    content.text = etree.CDATA(ontology.serialize(format="xml"))
    root.append(content)
    root.append(etree.Element("Pitfalls"))
    root.append(etree.Element("OutputFormat"))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", method="html")


@functools.cache
def _oops_pitfall_query():
    query = f"""SELECT ?element WHERE {{
        ?element {rdflib.RDF.type.n3()} {_OOPS.pitfall.n3()}.
        ?element {_OOPS.hasImportanceLevel.n3()} ?level.
    }}"""
    return rdflib.plugins.sparql.prepareQuery(query)


def check_pitfalls(
    ontology: rdflib.Graph,
    level: typing.Literal["Critical", "Important", "Minor"] = "Important",
) -> list[str]:
    """Check if an ontology does not contain pitfalls (of the given level)."""
    request = _oops_request_body(ontology=ontology)
    url = "https://oops.linkeddata.es/rest"
    response = requests.post(url=url, data=request)
    response.raise_for_status()
    results = rdflib.Graph()
    results.parse(response.content, format="xml")
    types = (_OOPS.pitfall, _OOPS.warning, _OOPS.suggestion)
    levels = ("Critical", "Important", "Minor")
    # fmt: off
    totals = {
        type_: len(list(results.subjects(predicate=rdflib.RDF.type, object=type_)))  # noqa: E501
        for type_ in types
    }
    query = _oops_pitfall_query()
    pitfalls = {
        level: len(list(results.query(query, initBindings={"level": rdflib.Literal(level, datatype=rdflib.XSD.string)})))  # noqa: E501
        for level in levels
    }
    # fmt: on
    if totals[_OOPS.pitfall] != sum(pitfalls.values()):
        raise Exception(
            "Sanity check failed. Maybe there is something wrong with OOPS!?"
        )
    if pitfalls[level] > 0:
        return [
            f"Too many {level.lower()} pitfalls found. "
            f"Check the ontology with https://oops.linkeddata.es/!"
        ]
    return []


def _is_owl(ontology: rdflib.Graph) -> bool:
    print(ontology)
    return (None, rdflib.RDF.type, rdflib.OWL.Ontology) in ontology


def main(argv: typing.Optional[typing.Sequence[str]] = None) -> int:
    # Setting up the parser
    parser = argparse.ArgumentParser(description="Check the provided ontologies")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="The names of the ontology files to check",
    )
    parser.add_argument(
        "--level",
        default="Important",
        choices=["Critical", "Important", "Minor"],
        help="The OOPS! importance level used to determine if ontology files with pitfalls pass the check or not",  # noqa: E501
    )
    args = parser.parse_args(argv)
    # Running the check
    retv = 0
    for filename in args.filenames:
        ontology = rdflib.Graph()
        ontology.parse(filename, format="turtle")
        errors = []
        # if _is_owl(ontology):
        errors.extend(check_consistency(ontology=ontology))
        errors.extend(check_pitfalls(ontology=ontology, level=args.level))
        if errors:
            retv = 1
        for error in errors:
            print(f"{filename}: { error }")
    return retv


if __name__ == "__main__":
    raise SystemExit(main())
